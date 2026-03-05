"""Activity Block Builder — converts raw captures into a rich timeline.

Replaces the old category-only aggregation with per-window, OCR-aware
activity blocks that give the coaching LLM much better signal about what
the user actually did.
"""
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ActivityBlock:
    """A contiguous chunk of activity on a single window/app."""
    start_time: int           # Unix timestamp
    end_time: int             # Unix timestamp
    duration_minutes: int     # Active time (idle excluded)
    app_name: str             # The actually-active app
    window_title: str         # Most common window title in block
    activity_label: str       # Compact: "email to Mike re: FMxAI"
    activity_type: str        # active_work, reading, communication, idle
    avg_change_ratio: float   # Engagement signal
    capture_count: int
    context_entities: List[str] = field(default_factory=list)
    ocr_snippet: str = ""     # Combined OCR content from the block
    background_apps: List[str] = field(default_factory=list)  # Non-active visible apps
    mode: str = ""            # "creating", "consuming", or "mixed"


@dataclass
class ActivityTimeline:
    """The full timeline for a digest period."""
    blocks: List[ActivityBlock]
    total_active_minutes: int
    total_idle_minutes: int
    context_switches: int
    top_apps: Dict[str, int]   # app_name → minutes
    time_range: str            # e.g. "09:00–18:30"


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

class ActivityBlockBuilder:
    """Builds an ActivityTimeline from raw DB captures."""

    # Gap between captures (in seconds) that triggers a block break
    GAP_FACTOR = 2.5
    # Number of consecutive idle captures before splitting
    IDLE_BREAK_COUNT = 3
    # Minimum change ratio to consider a window "active"
    ACTIVE_CHANGE_THRESHOLD = 0.02

    def __init__(self, capture_interval: int = 60):
        self.capture_interval = capture_interval
        self.gap_threshold = capture_interval * self.GAP_FACTOR

    # ---- public API -------------------------------------------------------

    def build_timeline(
        self,
        rows: List[Dict[str, Any]],
    ) -> ActivityTimeline:
        """Build a timeline from DB rows (from get_activity_metadata_timeline).

        Args:
            rows: List of row dicts with timestamp, app_name, window_title,
                  category, duration_seconds, metadata.

        Returns:
            ActivityTimeline ready for formatting.
        """
        if not rows:
            return ActivityTimeline(
                blocks=[], total_active_minutes=0, total_idle_minutes=0,
                context_switches=0, top_apps={}, time_range="",
            )

        # Stage 1: identify the "active window" per capture
        enriched = [self._identify_active_window(r) for r in rows]

        # Stage 2: group into raw blocks
        raw_blocks = self._group_into_blocks(enriched)

        # Stage 3: extract context and build ActivityBlock objects
        blocks = [self._build_block(rb) for rb in raw_blocks]

        # Stage 4: merge related blocks across brief interruptions
        blocks = self._merge_related_blocks(blocks)

        # Stage 5: compute timeline-level stats
        return self._build_timeline(blocks, rows)

    # ---- Stage 1: active window identification ----------------------------

    def _identify_active_window(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Determine which window was truly active in this capture.

        Uses per_window_changes from the inference metadata when available.
        Priority:
          1. Focused window with high change ratio
          2. Any window with highest change ratio
          3. Focused window with low change
          4. OS-reported app/title
        """
        meta = row.get("metadata") or {}
        inference = meta.get("processing", {})
        windows = meta.get("windows") or []

        # Get per-window change data from inference
        per_window_changes = inference.get("per_window_changes") or []
        # Also check top-level inference result
        if not per_window_changes:
            inf_data = meta.get("inference") or {}
            per_window_changes = inf_data.get("per_window_changes") or []

        # Build a lookup from (app, title) → change_ratio
        change_lookup = {}  # type: Dict[Tuple[str, str], float]
        for pwc in per_window_changes:
            key = (pwc.get("app_name", ""), pwc.get("window_title", ""))
            change_lookup[key] = pwc.get("change_ratio", 0.0)

        # Find focused window
        focused_win = None
        focused_change = 0.0
        best_change_win = None
        best_change_ratio = -1.0

        for w in windows:
            app = w.get("app_name", "")
            title = w.get("window_title", "")
            is_focused = w.get("focused", False)
            change = change_lookup.get((app, title), 0.0)

            if is_focused:
                focused_win = w
                focused_change = change

            if change > best_change_ratio:
                best_change_ratio = change
                best_change_win = w

        # Decide active window
        if focused_win and focused_change >= self.ACTIVE_CHANGE_THRESHOLD:
            active = focused_win
            change_ratio = focused_change
        elif best_change_win and best_change_ratio >= self.ACTIVE_CHANGE_THRESHOLD:
            active = best_change_win
            change_ratio = best_change_ratio
        elif focused_win:
            active = focused_win
            change_ratio = focused_change
        else:
            # Fallback to OS-reported
            active = None
            change_ratio = inference.get("change_ratio", 0.0)

        if active:
            active_app = active.get("app_name", row.get("app_name", ""))
            active_title = active.get("window_title", row.get("window_title", ""))
            active_ocr = active.get("ocr_text", "")
        else:
            active_app = row.get("app_name", "")
            active_title = row.get("window_title", "")
            active_ocr = ""

        # Determine activity type from inference
        activity_type_raw = inference.get("activity_type", row.get("category", "unknown"))
        is_idle = inference.get("activity_type") == "idle" and inference.get("idle_duration_captures", 0) >= self.IDLE_BREAK_COUNT

        return {
            **row,
            "active_app": active_app or "",
            "active_title": active_title or "",
            "active_ocr": active_ocr,
            "change_ratio": change_ratio,
            "is_idle": is_idle,
        }

    # ---- Stage 2: grouping ------------------------------------------------

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize window title for grouping (strip trailing noise)."""
        if not title:
            return ""
        # Remove common suffixes like "— Google Chrome", "- VS Code"
        for sep in [" — ", " - ", " | "]:
            parts = title.rsplit(sep, 1)
            if len(parts) == 2 and len(parts[1]) < 30:
                title = parts[0]
                break
        return title.strip()

    def _group_into_blocks(
        self, enriched: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """Group consecutive captures with same active window into blocks."""
        if not enriched:
            return []

        blocks = []  # type: List[List[Dict[str, Any]]]
        current_block = [enriched[0]]

        for i in range(1, len(enriched)):
            prev = enriched[i - 1]
            curr = enriched[i]

            # Check for block break conditions
            time_gap = curr["timestamp"] - prev["timestamp"]
            same_window = (
                curr["active_app"] == prev["active_app"]
                and self._normalize_title(curr["active_title"])
                == self._normalize_title(prev["active_title"])
            )

            # Count consecutive idles at end of current block
            idle_count = 0
            for r in reversed(current_block):
                if r.get("is_idle"):
                    idle_count += 1
                else:
                    break

            should_break = (
                not same_window
                or time_gap > self.gap_threshold
                or idle_count >= self.IDLE_BREAK_COUNT
            )

            if should_break:
                blocks.append(current_block)
                current_block = [curr]
            else:
                current_block.append(curr)

        if current_block:
            blocks.append(current_block)

        return blocks

    # ---- Stage 3: block building ------------------------------------------

    def _build_block(self, captures: List[Dict[str, Any]]) -> ActivityBlock:
        """Convert a group of captures into an ActivityBlock."""
        start_time = captures[0]["timestamp"]
        end_time = captures[-1]["timestamp"]

        # Most common title
        title_counter = Counter(
            self._normalize_title(c.get("active_title", "")) for c in captures
        )
        window_title = title_counter.most_common(1)[0][0] if title_counter else ""

        app_name = captures[0].get("active_app", "")

        # Active vs idle time
        active_captures = [c for c in captures if not c.get("is_idle")]
        idle_captures = [c for c in captures if c.get("is_idle")]
        duration_seconds = sum(c.get("duration_seconds", 60) for c in active_captures)
        duration_minutes = max(1, duration_seconds // 60)

        # Average change ratio (engagement)
        changes = [c.get("change_ratio", 0.0) for c in active_captures]
        avg_change = sum(changes) / len(changes) if changes else 0.0

        # Determine activity type
        if len(idle_captures) > len(active_captures):
            activity_type = "idle"
        elif avg_change >= 0.10:
            activity_type = "active_work"
        elif avg_change >= 0.02:
            activity_type = "reading"
        else:
            activity_type = "idle"

        # Extract context
        ocr_texts = [c.get("active_ocr", "") for c in captures if c.get("active_ocr")]
        activity_label, entities = self._extract_context(
            app_name, window_title, ocr_texts
        )

        # If app is "Other" but we inferred a real activity, upgrade the app name
        if app_name.lower() in ("other", "unknown", "") and activity_label.startswith("video call"):
            app_name = "Video Call"
            window_title = activity_label

        # Combine OCR content across captures
        ocr_snippet = self._pick_best_snippet(ocr_texts)

        # Background apps: non-active windows visible during this block
        background_apps = self._extract_background_apps(captures, app_name)

        # Creation vs consumption mode
        mode = self._infer_mode(app_name, avg_change, activity_type)

        return ActivityBlock(
            start_time=start_time,
            end_time=end_time,
            duration_minutes=duration_minutes,
            app_name=app_name,
            window_title=window_title,
            activity_label=activity_label,
            activity_type=activity_type,
            avg_change_ratio=round(avg_change, 3),
            capture_count=len(captures),
            context_entities=entities,
            ocr_snippet=ocr_snippet,
            background_apps=background_apps,
            mode=mode,
        )

    @staticmethod
    def _extract_background_apps(
        captures: List[Dict[str, Any]], active_app: str
    ) -> List[str]:
        """Collect non-active apps that were visible during this block."""
        bg_counter = Counter()  # type: Counter
        for c in captures:
            meta = c.get("metadata") or {}
            windows = meta.get("windows") or []
            for w in windows:
                wapp = w.get("app_name", "")
                if wapp and wapp != active_app and wapp != "Other":
                    title = w.get("window_title", "")
                    # Use app + short title for grouping
                    label = wapp
                    if title:
                        short = title[:40].split(" — ")[0].split(" - ")[0].strip()
                        if short:
                            label = f"{wapp}: {short}"
                    bg_counter[label] += 1
        # Return those seen in at least 2 captures (or all if block is short)
        threshold = 2 if len(captures) > 2 else 1
        return [app for app, count in bg_counter.most_common(5) if count >= threshold]

    @staticmethod
    def _infer_mode(app_name: str, avg_change: float, activity_type: str) -> str:
        """Infer whether the user was creating or consuming content.

        - creating: high change ratio in an editor, doc, email compose, chat
        - consuming: low change ratio, or browser/PDF reading
        - mixed: moderate change (scrolling + occasional typing)
        """
        app_lower = app_name.lower()

        # Editors and terminals with high change = creating
        creators = ["code", "pycharm", "intellij", "xcode", "vim", "emacs",
                     "sublime", "cursor", "terminal", "iterm", "obsidian",
                     "notion", "warp"]
        is_creator_app = any(c in app_lower for c in creators)

        if avg_change >= 0.15 and is_creator_app:
            return "creating"
        if avg_change >= 0.15:
            # High change in non-editor = likely composing (email, chat, doc)
            return "creating"
        if avg_change < 0.05:
            return "consuming"
        return "mixed"

    # ---- Stage 4: context extraction --------------------------------------

    def _extract_context(
        self,
        app_name: str,
        window_title: str,
        ocr_texts: List[str],
    ) -> Tuple[str, List[str]]:
        """Extract a compact activity label and entities from app + OCR.

        Returns:
            (activity_label, context_entities)
        """
        app_lower = app_name.lower()
        entities = []  # type: List[str]
        combined_ocr = " ".join(ocr_texts[:3])[:500]  # Cap for performance

        # Infer real activity when app is "Other" or unrecognized
        if app_lower in ("other", "unknown", ""):
            label = self._infer_from_ocr(combined_ocr)
            if label:
                return label, entities

        # Email apps
        if any(kw in app_lower for kw in ["mail", "superhuman", "spark"]) or \
           any(kw in window_title.lower() for kw in ["gmail", "inbox", "outlook"]):
            label = self._extract_email_context(window_title, combined_ocr)
            # Extract people from email
            people = self._extract_people(combined_ocr)
            if people:
                entities.extend(people[:3])
            return label, entities

        # Chat / messaging
        if any(kw in app_lower for kw in ["slack", "discord", "messages", "telegram"]):
            label = self._extract_chat_context(window_title, combined_ocr)
            people = self._extract_people(combined_ocr)
            if people:
                entities.extend(people[:2])
            return label, entities

        # Code editors
        if any(kw in app_lower for kw in ["code", "pycharm", "intellij", "xcode",
                                           "vim", "emacs", "sublime", "cursor"]):
            label = self._extract_editor_context(window_title)
            return label, entities

        # Terminal
        if any(kw in app_lower for kw in ["terminal", "iterm", "kitty", "alacritty",
                                           "warp"]):
            return "terminal session", entities

        # Browsers — use page title
        browsers = ["chrome", "safari", "firefox", "arc", "edge", "brave"]
        if any(b in app_lower for b in browsers):
            label = self._extract_browser_context(window_title)
            return label, entities

        # Generic: use cleaned window title
        if window_title:
            return self._clean_title(window_title), entities

        return app_name or "unknown", entities

    @staticmethod
    def _infer_from_ocr(ocr: str) -> Optional[str]:
        """Try to infer the real activity from OCR when app is 'Other'.

        Looks for telltale patterns from common apps whose windows may not
        appear in the spatial mapper (e.g. Zoom, notifications).
        """
        if not ocr:
            return None
        ocr_lower = ocr.lower()

        # Video call patterns (Zoom, Meet, Teams)
        call_patterns = [
            r'\d+m\s*left',           # "50m left" countdown
            r'join\s+zoom',
            r'zoom\s+meeting',
            r'leave\s+meeting',
            r'mute|unmute',
            r'share\s+screen',
            r'google\s+meet',
            r'teams\s+meeting',
        ]
        if any(re.search(p, ocr_lower) for p in call_patterns):
            # Try to extract participant names
            name_match = re.search(r'([A-Z][a-z]+ [A-Z][a-z]+).*(?:left|now)', ocr)
            if name_match:
                return f"video call with {name_match.group(1)}"
            return "video call"

        # Notification center patterns
        if re.search(r'(?:notification|do not disturb)', ocr_lower):
            return "viewing notifications"

        return None

    @staticmethod
    def _extract_email_context(title: str, ocr: str) -> str:
        """Extract email context like 'email to Mike re: FMxAI'."""
        # Try to find subject from window title
        title_lower = title.lower()
        if " - " in title:
            parts = title.split(" - ")
            subject = parts[0].strip()
            if len(subject) > 5:
                return f"email: {subject[:50]}"

        # Try OCR for subject line
        subject_match = re.search(r'(?:subject|re):\s*(.{5,60})', ocr, re.IGNORECASE)
        if subject_match:
            return f"email: {subject_match.group(1).strip()[:50]}"

        if "inbox" in title_lower:
            return "reading email inbox"
        if "compose" in title_lower or "new message" in title_lower:
            return "composing email"

        return "email"

    @staticmethod
    def _extract_chat_context(title: str, ocr: str) -> str:
        """Extract chat context like 'Slack #general' or 'DM with Mike'."""
        # Slack: "#channel | Workspace"
        channel_match = re.search(r'#([\w-]+)', title)
        if channel_match:
            return f"chat: #{channel_match.group(1)}"

        # DM pattern
        if "dm" in title.lower() or "direct message" in title.lower():
            return "direct message"

        # Use first meaningful part of title
        if " | " in title:
            return f"chat: {title.split(' | ')[0].strip()[:40]}"
        if " - " in title:
            return f"chat: {title.split(' - ')[0].strip()[:40]}"

        return "messaging"

    @staticmethod
    def _extract_editor_context(title: str) -> str:
        """Extract editor context like 'editing spatial.py'."""
        # VS Code: "filename.ext - project — Visual Studio Code"
        # PyCharm: "filename.ext – project"
        for sep in [" — ", " – ", " - "]:
            if sep in title:
                filename = title.split(sep)[0].strip()
                # Check if it looks like a filename
                if "." in filename and len(filename) < 80:
                    return f"editing {filename}"
                break

        if title:
            return f"editing: {title[:50]}"
        return "coding"

    @staticmethod
    def _extract_browser_context(title: str) -> str:
        """Extract browser context from page title."""
        # Remove browser suffix
        for suffix in ["- Google Chrome", "- Chrome", "— Mozilla Firefox",
                       "- Firefox", "- Safari", "- Arc", "- Microsoft Edge",
                       "- Brave"]:
            if title.endswith(suffix):
                title = title[:-len(suffix)].strip()
                break

        if title:
            return title[:60]
        return "browsing"

    @staticmethod
    def _clean_title(title: str) -> str:
        """Clean window title for use as activity label."""
        # Remove app name suffixes
        for sep in [" — ", " – ", " - ", " | "]:
            if sep in title:
                parts = title.split(sep)
                if len(parts[-1]) < 30:
                    title = sep.join(parts[:-1])
                break
        return title.strip()[:60] or "unknown"

    @staticmethod
    def _extract_people(text: str) -> List[str]:
        """Extract person names from OCR text (simple heuristic)."""
        # Look for "From: Name", "To: Name", "@name" patterns
        people = []
        for pattern in [
            r'(?:from|to|cc):\s*([A-Z][a-z]+ [A-Z][a-z]+)',
            r'@(\w{3,20})',
        ]:
            matches = re.findall(pattern, text, re.IGNORECASE)
            people.extend(matches[:3])
        return list(dict.fromkeys(people))[:5]  # Dedupe, cap at 5

    @staticmethod
    def _is_incoherent(segment: str) -> bool:
        """Check if a text segment is OCR garbage (garbled, not real words)."""
        s = segment.strip()
        if not s or len(s) < 3:
            return True
        # Count alphabetic characters
        alpha_count = sum(1 for c in s if c.isalpha())
        if len(s) > 0 and alpha_count / len(s) < 0.3:
            return True
        # Split into "words" and check average length & coherence
        words = s.split()
        if not words:
            return True
        avg_word_len = sum(len(w) for w in words) / len(words)
        # Very short average = garbled single chars; very long = no spaces
        if avg_word_len < 1.5 and len(words) > 2:
            return True
        # Single "word" that's mostly non-alpha
        if len(words) == 1 and len(s) > 3:
            if alpha_count / len(s) < 0.5:
                return True
        return False

    @classmethod
    def _clean_ocr(cls, text: str) -> str:
        """Clean up raw OCR text: strip menu bar junk, garbled text, collapse whitespace."""
        if not text:
            return ""
        # Remove common macOS menu bar / chrome lines
        lines = text.split("\n")
        cleaned = []
        skip_patterns = [
            r'^(File|Edit|View|Window|Help|History|Bookmarks|Profiles|Tools)\b',
            r'^\s*[\-\*•]\s*$',          # Bullet-only lines
            r'^\d{1,2}:\d{2}\s*(AM|PM)',  # Menu bar clock
            r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\w+\s+\d',  # Date in menu bar
            r'^::\s*\d+%',               # Battery percentage
            r'^\d+%\s*$',               # Standalone percentage
            r'^\w{1,3}$',               # Very short junk tokens
        ]
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if any(re.match(p, line, re.IGNORECASE) for p in skip_patterns):
                continue
            cleaned.append(line)

        joined = " | ".join(cleaned)

        # Pass 2: replace incoherent segments with marker, collapsing consecutive
        segments = [s.strip() for s in joined.split(" | ") if s.strip()]
        result = []
        prev_incoherent = False
        for seg in segments:
            if cls._is_incoherent(seg):
                if not prev_incoherent:
                    result.append("<<incoherent>>")
                prev_incoherent = True
            else:
                result.append(seg)
                prev_incoherent = False

        return " | ".join(result)

    @classmethod
    def _pick_best_snippet(cls, ocr_texts: List[str], max_len: int = 0) -> str:
        """Combine OCR from all captures in a block, deduplicating content.

        Cleans each capture's OCR, then appends only the parts that are new
        (not already present in the running text). This captures content the
        user scrolled through or typed across multiple captures.

        Args:
            ocr_texts: Raw OCR strings from each capture in the block.
            max_len: Maximum length (0 = unlimited).
        """
        if not ocr_texts:
            return ""

        # Clean each capture
        cleaned = [cls._clean_ocr(t) for t in ocr_texts]
        cleaned = [c for c in cleaned if c]
        if not cleaned:
            return ""

        # Start with the first capture, then append novel segments
        combined = cleaned[0]
        for text in cleaned[1:]:
            # Split into segments and append ones not already in combined
            segments = [s.strip() for s in text.split(" | ") if s.strip()]
            novel = [s for s in segments if s not in combined]
            if novel:
                combined += " | " + " | ".join(novel)

        if max_len and len(combined) > max_len:
            combined = combined[:max_len].rsplit(" ", 1)[0] + "..."

        return combined

    # ---- Stage 4: merge related blocks ------------------------------------

    # Maximum duration of an interruption (minutes) that we'll merge across
    MERGE_INTERRUPTION_MAX = 3

    @classmethod
    def _merge_related_blocks(cls, blocks: List[ActivityBlock]) -> List[ActivityBlock]:
        """Merge blocks on the same app/topic separated by brief interruptions.

        If block A is on "Firefox: Atlas doc", then block B is 1-2 min on
        "Other" or "Beeper", then block C is back on "Firefox: Atlas doc",
        merge A and C into one block and note B as an interruption in
        the background_apps.
        """
        if len(blocks) < 3:
            return blocks

        merged = [blocks[0]]

        i = 1
        while i < len(blocks):
            prev = merged[-1]
            curr = blocks[i]

            # Check if we can merge curr into prev across a brief interruption
            # Look ahead: is curr a short block and the one after it matches prev?
            if (i + 1 < len(blocks)
                and curr.duration_minutes <= cls.MERGE_INTERRUPTION_MAX
                and cls._blocks_same_topic(prev, blocks[i + 1])):
                # curr is a brief interruption — absorb it and the next block
                nxt = blocks[i + 1]
                merged[-1] = cls._merge_two_blocks(prev, nxt, interruption=curr)
                i += 2
                continue

            # Check if curr is same topic as prev (adjacent, no gap)
            if cls._blocks_same_topic(prev, curr):
                merged[-1] = cls._merge_two_blocks(prev, curr)
                i += 1
                continue

            merged.append(curr)
            i += 1

        return merged

    @staticmethod
    def _blocks_same_topic(a: ActivityBlock, b: ActivityBlock) -> bool:
        """Check if two blocks are on the same app and similar topic."""
        if a.app_name != b.app_name:
            return False
        # Same app — check if titles are related
        # Normalize and compare
        a_norm = a.window_title.lower().strip()
        b_norm = b.window_title.lower().strip()
        if not a_norm or not b_norm:
            return a.app_name == b.app_name  # Same app, no title = merge
        # Exact match or one contains the other
        if a_norm == b_norm:
            return True
        if a_norm in b_norm or b_norm in a_norm:
            return True
        return False

    @staticmethod
    def _merge_two_blocks(
        a: ActivityBlock,
        b: ActivityBlock,
        interruption: Optional[ActivityBlock] = None,
    ) -> ActivityBlock:
        """Merge two related blocks into one, optionally absorbing an interruption."""
        # Combine OCR (deduplicate)
        combined_ocr = a.ocr_snippet
        if b.ocr_snippet:
            # Append segments from b that aren't already in a
            b_segments = [s.strip() for s in b.ocr_snippet.split(" | ") if s.strip()]
            novel = [s for s in b_segments if s not in combined_ocr]
            if novel:
                combined_ocr += " | " + " | ".join(novel)

        # Combine background apps
        bg = list(a.background_apps)
        for app in b.background_apps:
            if app not in bg:
                bg.append(app)
        if interruption:
            interr_label = f"{interruption.app_name}: {interruption.activity_label}"
            if interr_label not in bg:
                bg.append(interr_label)

        # Use whichever has the longer/richer label
        label = a.activity_label if len(a.activity_label) >= len(b.activity_label) else b.activity_label

        # Weighted average change ratio
        total_caps = a.capture_count + b.capture_count
        avg_change = (
            (a.avg_change_ratio * a.capture_count + b.avg_change_ratio * b.capture_count)
            / total_caps
        ) if total_caps else 0.0

        total_mins = a.duration_minutes + b.duration_minutes

        # Mode: if either is creating, the merged block is creating
        if a.mode == "creating" or b.mode == "creating":
            mode = "creating"
        elif a.mode == "mixed" or b.mode == "mixed":
            mode = "mixed"
        else:
            mode = a.mode or b.mode

        # Activity type from the dominant block
        if total_mins > 0:
            if a.activity_type == "active_work" or b.activity_type == "active_work":
                activity_type = "active_work"
            elif a.activity_type == "reading" or b.activity_type == "reading":
                activity_type = "reading"
            else:
                activity_type = a.activity_type
        else:
            activity_type = a.activity_type

        # Combine entities
        entities = list(a.context_entities)
        for e in b.context_entities:
            if e not in entities:
                entities.append(e)

        return ActivityBlock(
            start_time=a.start_time,
            end_time=b.end_time,
            duration_minutes=total_mins,
            app_name=a.app_name,
            window_title=a.window_title or b.window_title,
            activity_label=label,
            activity_type=activity_type,
            avg_change_ratio=round(avg_change, 3),
            capture_count=total_caps,
            context_entities=entities,
            ocr_snippet=combined_ocr,
            background_apps=bg,
            mode=mode,
        )

    # ---- Timeline assembly ------------------------------------------------

    def _build_timeline(
        self,
        blocks: List[ActivityBlock],
        rows: List[Dict[str, Any]],
    ) -> ActivityTimeline:
        """Assemble final timeline with stats."""
        total_active = sum(b.duration_minutes for b in blocks if b.activity_type != "idle")
        total_idle = sum(b.duration_minutes for b in blocks if b.activity_type == "idle")

        # Count context switches (app changes between consecutive blocks)
        switches = 0
        for i in range(1, len(blocks)):
            if blocks[i].app_name != blocks[i - 1].app_name:
                switches += 1

        # Top apps by active minutes
        app_minutes = Counter()  # type: Counter
        for b in blocks:
            if b.activity_type != "idle":
                app_minutes[b.app_name] += b.duration_minutes

        # Time range string
        if rows:
            start_dt = datetime.fromtimestamp(rows[0]["timestamp"])
            end_dt = datetime.fromtimestamp(rows[-1]["timestamp"])
            time_range = f"{start_dt.strftime('%H:%M')}\u2013{end_dt.strftime('%H:%M')}"
        else:
            time_range = ""

        return ActivityTimeline(
            blocks=blocks,
            total_active_minutes=total_active,
            total_idle_minutes=total_idle,
            context_switches=switches,
            top_apps=dict(app_minutes.most_common(10)),
            time_range=time_range,
        )


# ---------------------------------------------------------------------------
# Formatter
# ---------------------------------------------------------------------------

class ActivityBlockFormatter:
    """Formats an ActivityTimeline into text for the LLM prompt."""

    # Maximum consecutive short blocks (≤2 min) on the same app before compressing
    _SHORT_BLOCK_THRESHOLD = 2  # minutes
    _MIN_RUN_TO_COMPRESS = 3   # need at least 3 consecutive to compress

    @classmethod
    def format_for_prompt(
        cls,
        timeline: ActivityTimeline,
        period: str = "day",
        include_ocr: bool = True,
    ) -> str:
        """Format timeline as text for the digest prompt.

        All blocks are included (no cap). Consecutive short blocks on the
        same app are compressed into a single summary line to save tokens.

        Args:
            timeline: The built timeline.
            period: "day" or "week" — affects filtering.
            include_ocr: Include cleaned OCR snippets for each block.

        Returns:
            Formatted text for the LLM prompt.
        """
        if not timeline.blocks:
            return "No activity data available for this period."

        lines = []

        # Header
        total = timeline.total_active_minutes + timeline.total_idle_minutes
        lines.append(
            f"**Total Tracked Time:** {total} min "
            f"({timeline.total_active_minutes} active, "
            f"{timeline.total_idle_minutes} idle)"
        )
        if timeline.time_range:
            lines.append(f"**Time Range:** {timeline.time_range}")
        lines.append(f"**Context Switches:** {timeline.context_switches}")
        lines.append("")

        # Top apps
        if timeline.top_apps:
            app_parts = [f"{app} ({mins}min)" for app, mins in
                         sorted(timeline.top_apps.items(), key=lambda x: -x[1])[:5]]
            lines.append(f"**Top Apps:** {', '.join(app_parts)}")
            lines.append("")

        # Filter for weekly
        blocks = timeline.blocks
        if period == "week":
            blocks = [b for b in blocks if b.duration_minutes >= 5]

        # Group blocks into runs: consecutive short blocks on same app get compressed
        lines.append("**Activity Timeline:**")
        i = 0
        while i < len(blocks):
            block = blocks[i]

            # Look ahead for a run of short blocks on the same app
            if block.duration_minutes <= cls._SHORT_BLOCK_THRESHOLD:
                run = [block]
                j = i + 1
                while j < len(blocks):
                    nxt = blocks[j]
                    if (nxt.duration_minutes <= cls._SHORT_BLOCK_THRESHOLD
                            and nxt.app_name == block.app_name):
                        run.append(nxt)
                        j += 1
                    else:
                        break

                if len(run) >= cls._MIN_RUN_TO_COMPRESS:
                    # Compress the run into one summary line
                    cls._format_compressed_run(run, lines, include_ocr)
                    i = j
                    continue

            # Normal block — full detail
            cls._format_single_block(block, lines, include_ocr)
            i += 1

        return "\n".join(lines)

    @staticmethod
    def _format_single_block(
        block: ActivityBlock,
        lines: List[str],
        include_ocr: bool,
    ) -> None:
        """Append formatted lines for a single block."""
        start_str = datetime.fromtimestamp(block.start_time).strftime("%H:%M")
        end_str = datetime.fromtimestamp(block.end_time).strftime("%H:%M")

        engagement = "high" if block.avg_change_ratio >= 0.15 else \
                    "med" if block.avg_change_ratio >= 0.05 else "low"

        mode_tag = f" [{block.mode}]" if block.mode else ""
        entry = (
            f"- {start_str}\u2013{end_str} {block.app_name}: "
            f"{block.activity_label} "
            f"({block.duration_minutes}min, {engagement}{mode_tag})"
        )
        lines.append(entry)

        if block.background_apps:
            bg_str = ", ".join(block.background_apps[:3])
            lines.append(f"  [also visible: {bg_str}]")

        if include_ocr and block.ocr_snippet:
            lines.append(f"  > {block.ocr_snippet}")

    @staticmethod
    def _format_compressed_run(
        run: List[ActivityBlock],
        lines: List[str],
        include_ocr: bool,
    ) -> None:
        """Compress a run of consecutive short blocks on the same app."""
        start_str = datetime.fromtimestamp(run[0].start_time).strftime("%H:%M")
        end_str = datetime.fromtimestamp(run[-1].end_time).strftime("%H:%M")
        app = run[0].app_name
        total_min = sum(b.duration_minutes for b in run)
        n = len(run)

        # Collect unique activity labels
        labels = list(dict.fromkeys(b.activity_label for b in run))
        label_str = ", ".join(labels[:4])
        if len(labels) > 4:
            label_str += f", +{len(labels) - 4} more"

        # Aggregate engagement
        avg_change = sum(b.avg_change_ratio for b in run) / n
        engagement = "high" if avg_change >= 0.15 else \
                    "med" if avg_change >= 0.05 else "low"

        # Dominant mode
        mode_counts = Counter(b.mode for b in run if b.mode)
        mode = mode_counts.most_common(1)[0][0] if mode_counts else ""
        mode_tag = f" [{mode}]" if mode else ""

        lines.append(
            f"- {start_str}\u2013{end_str} {app}: [{n} quick views] "
            f"{label_str} ({total_min}min total, {engagement}{mode_tag})"
        )

        # Collect unique background apps across the run
        all_bg = []  # type: List[str]
        for b in run:
            for bg in b.background_apps:
                if bg not in all_bg:
                    all_bg.append(bg)
        if all_bg:
            lines.append(f"  [also visible: {', '.join(all_bg[:3])}]")

        # Combine OCR from all blocks in run, deduplicated
        if include_ocr:
            all_snippets = [b.ocr_snippet for b in run if b.ocr_snippet]
            if all_snippets:
                # Collect unique segments across all blocks
                seen = set()  # type: set
                combined_segs = []  # type: List[str]
                for snippet in all_snippets:
                    for seg in snippet.split(" | "):
                        seg = seg.strip()
                        if seg and seg not in seen:
                            seen.add(seg)
                            combined_segs.append(seg)
                if combined_segs:
                    combined = " | ".join(combined_segs)
                    if len(combined) > 500:
                        combined = combined[:500].rsplit(" | ", 1)[0] + " | ..."
                    lines.append(f"  > {combined}")

    @staticmethod
    def format_for_display(timeline: ActivityTimeline) -> str:
        """Format timeline for human-readable CLI display (pre/post scrub debug)."""
        if not timeline.blocks:
            return "No activity data."

        lines = [
            f"Timeline: {timeline.time_range}",
            f"Active: {timeline.total_active_minutes}min  "
            f"Idle: {timeline.total_idle_minutes}min  "
            f"Switches: {timeline.context_switches}",
            "",
        ]

        for block in timeline.blocks:
            start_str = datetime.fromtimestamp(block.start_time).strftime("%H:%M")
            end_str = datetime.fromtimestamp(block.end_time).strftime("%H:%M")
            mode_str = f" [{block.mode}]" if block.mode else ""
            lines.append(
                f"  {start_str}-{end_str}  {block.app_name:20s}  "
                f"{block.activity_label[:40]:40s}  "
                f"{block.duration_minutes:3d}min  "
                f"chg={block.avg_change_ratio:.2f}{mode_str}"
            )
            if block.background_apps:
                lines.append(f"    also visible: {', '.join(block.background_apps[:3])}")

        return "\n".join(lines)
