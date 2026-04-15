"""
ARQ asynchronous task definitions.
Phase 0 establishes the framework and helper utilities, Phase 2 implements file processing, and later phases fill in the remaining tasks.
"""
import asyncio
import os
from datetime import datetime, timezone
from typing import Optional
from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.models.ai_task import AITask
from app.models.toe import TOEFile
from sqlmodel import select


# ── Progress update tools ──────────────────────────────────────────

async def update_task_progress(task_id: str, message: str):
    """Update task progress message"""
    async with AsyncSessionLocal() as db:
        result = await db.exec(select(AITask).where(AITask.id == task_id))
        task = result.first()
        if task:
            task.status = "running"
            task.progress_message = message
            db.add(task)
            await db.commit()


async def finish_task(task_id: str, summary: str, download_url: Optional[str] = None):
    """Mark task as completed"""
    async with AsyncSessionLocal() as db:
        result = await db.exec(select(AITask).where(AITask.id == task_id))
        task = result.first()
        if task:
            task.status = "done"
            task.result_summary = summary
            task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            if download_url:
                task.download_url = download_url
            db.add(task)
            await db.commit()


async def fail_task(task_id: str, error: str):
    """Mark task as failed"""
    async with AsyncSessionLocal() as db:
        result = await db.exec(select(AITask).where(AITask.id == task_id))
        task = result.first()
        if task:
            task.status = "failed"
            task.error_message = error
            task.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.add(task)
            await db.commit()


def _normalize_sfr_source(value: Optional[str]) -> str:
    normalized = (value or "manual").strip().lower()
    if normalized in {"manual", "ai", "st_pp"}:
        return normalized
    if normalized in {"st/pp", "stpp", "st-pp"}:
        return "st_pp"
    if normalized in {"standard", "custom"}:
        return "manual"
    return "manual"


def _parse_sfr_dependencies(value: Optional[str]) -> list[str]:
    if not value:
        return []
    result: list[str] = []
    for part in value.split(","):
        dep = part.strip().split(" ", 1)[0].strip().upper()
        if dep and dep not in {"NONE", "NO"}:
            result.append(dep)
    return list(dict.fromkeys(result))


def _extract_sfr_codes_from_text(text: str) -> list[str]:
    import re

    pattern = re.compile(r"\b(F[A-Z]{2}_[A-Z]{3}\.\d+(?:/[A-Z0-9_-]+)?)\b", re.IGNORECASE)
    return list(dict.fromkeys(match.group(1).upper() for match in pattern.finditer(text or "")))


def _build_st_pp_objective_context(text: str, objective_code: str, objective_description: Optional[str], max_chars: int = 18000) -> str:
    import re

    source = text or ""
    upper_source = source.upper()
    snippets: list[str] = []
    code = (objective_code or "").strip().upper()

    if code:
        start = 0
        while True:
            index = upper_source.find(code, start)
            if index < 0:
                break
            left = max(0, index - 1600)
            right = min(len(source), index + 3200)
            snippets.append(source[left:right])
            start = index + len(code)
            if len("\n\n".join(snippets)) >= max_chars:
                break

    if not snippets and objective_description:
        keywords = [
            item.lower()
            for item in re.findall(r"[A-Za-z]{4,}", objective_description)
            if item.strip()
        ]
        for keyword in list(dict.fromkeys(keywords))[:6]:
            index = source.lower().find(keyword)
            if index < 0:
                continue
            left = max(0, index - 1200)
            right = min(len(source), index + 2600)
            snippets.append(source[left:right])
            if len("\n\n".join(snippets)) >= max_chars:
                break

    heading_pattern = re.compile(
        r"(?:^|\n)\s*\d*\.?\d*\s*(Security\s+Objectives|Security\s+(?:Functional\s+)?Requirements|SFRs\s+Rationale)",
        re.IGNORECASE,
    )
    for match in heading_pattern.finditer(source):
        left = match.start()
        right = min(len(source), match.start() + 4000)
        snippets.append(source[left:right])
        if len("\n\n".join(snippets)) >= max_chars:
            break

    if not snippets:
        return source[:max_chars]

    combined = "\n\n---\n\n".join(snippets)
    return combined[:max_chars]


# ── B2-6: File content extraction task ────────────────────────────────

async def _get_pdf_timeout() -> int:
    """Read PDF parsing timeout setting from database, fall back to config default."""
    try:
        from app.models.system_setting import SystemSetting
        async with AsyncSessionLocal() as db:
            result = await db.exec(
                select(SystemSetting).where(SystemSetting.key == "pdf_parse_timeout_seconds")
            )
            row = result.first()
            if row:
                return int(row.value)
    except Exception:
        pass
    return settings.pdf_parse_timeout_seconds


async def _get_import_timeout(default_timeout: Optional[int] = None) -> int:
    """Timeout budget for import-type tasks; defaults to at least system PDF Parse Timeout configuration."""
    system_timeout = await _get_pdf_timeout()
    if default_timeout is None:
        return system_timeout
    try:
        return max(int(default_timeout), int(system_timeout))
    except Exception:
        return system_timeout


def _extract_pdf_sync(file_path: str) -> str:
    """Synchronous PDF text extraction for run_in_executor, with multiple fallback methods."""
    # Method 1: pypdf
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        texts = [page.extract_text() or "" for page in reader.pages]
        result = "\n\n".join(t for t in texts if t.strip())
        if result.strip():
            return result
    except Exception:
        pass
    # Method 2: pdfplumber (better for scanned / complex layout PDFs)
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            texts = [p.extract_text() or "" for p in pdf.pages]
        result = "\n\n".join(t for t in texts if t.strip())
        if result.strip():
            return result
    except Exception:
        pass
    # Method 3: Force read as text (some PDFs are essentially text streams)
    try:
        with open(file_path, "rb") as f:
            raw = f.read()
        import re
        chunks = re.findall(rb"\(([^\)]{4,})\)", raw)
        text = b" ".join(chunks).decode("latin-1", errors="ignore")
        if len(text.strip()) > 100:
            return text
    except Exception:
        pass
    return ""


async def _extract_document_text(file_path: str, mime_type: str) -> str:
    """Extract text from a document using multiple fallbacks. PDFs use a dedicated timeout."""

    # ── PDF ──
    if mime_type == "application/pdf":
        pdf_timeout = await _get_pdf_timeout()
        loop = asyncio.get_event_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, _extract_pdf_sync, file_path),
                timeout=float(pdf_timeout),
            )
        except asyncio.TimeoutError:
            return f"[PDF parsing timed out after {pdf_timeout} seconds. Increase the PDF parsing timeout in settings or check whether the file is too large.]"

    # ── Word ──
    if mime_type in (
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ):
        try:
            from docx import Document
            doc = Document(file_path)
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception:
            pass
        # Fallback: unzip as word/document.xml
        try:
            import zipfile, re
            with zipfile.ZipFile(file_path) as z:
                with z.open("word/document.xml") as f:
                    xml = f.read().decode("utf-8", errors="ignore")
            text = re.sub(r"<[^>]+>", " ", xml)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 50:
                return text
        except Exception:
            pass
        return ""

    # ── HTML ──
    if mime_type in ("text/html", "application/xhtml+xml"):
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html = f.read()
            # Remove script/style blocks before extracting text
            import re
            html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"&[a-z]+;", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return text
        except Exception:
            return ""


def _extract_pdf_toc_and_page_content(file_path: str, section_keywords: list[str]) -> dict[str, str]:
    """
    Extract the table of contents and requested section content from a PDF based on page ranges.

    Args:
        file_path: PDF file path
        section_keywords: List of section keywords to extract

    Returns:
        dict: {section_name: extracted_text}
    """
    result = {}
    
    try:
        from pypdf import PdfReader
        import re
        
        reader = PdfReader(file_path)
        total_pages = len(reader.pages)
        
        # Extract all page text and record page numbers
        all_pages_text = []
        for page_num, page in enumerate(reader.pages):
            try:
                text = page.extract_text() or ""
                all_pages_text.append((page_num, text))
            except:
                all_pages_text.append((page_num, ""))
        
        # Build complete text and mark page boundaries
        full_text = ""
        page_boundaries = {}  # Record start position of each page in full_text
        for page_num, text in all_pages_text:
            page_boundaries[page_num] = len(full_text)
            full_text += text + "\n\n"
        
        # === Core improvement: Intelligently skip TOC section and entries ===
        # Find the end of TOC section (typically after "Table of Contents" and series of TOC entries)
        toc_end_marker = None
        toc_patterns = [
            r'(?i)(Table of Contents|Contents)',
              r'(?i)(Table des Matières|Sommaire)',
        ]
        for pattern in toc_patterns:
            match = re.search(pattern, full_text)
            if match:
                # TOC usually occurs within 50-100 lines after "Table of Contents" text
                # Find position of next actual content section (not TOC) after that
                toc_start = match.start()
                # Search after TOC for true first chapter (no ... and page numbers)
                search_region = full_text[toc_start:min(toc_start + 50000, len(full_text))]
                # Find numbered sections without "..."
                chapter_match = re.search(r'\n\s*\d+\.\d+(?:\.\d+)?\s+\w+[^\.]*[^0-9]\n(?!\s*\d+\.\d+)', search_region)
                if chapter_match:
                    toc_end_marker = toc_start + chapter_match.end()
                    break
        
        # Extract page stream text (skip TOC section)
        # Start from first page that looks like actual content
        content_start_page = 0
        for page_num in range(min(10, total_pages)):  # Check first 10 pages
            text = all_pages_text[page_num][1].lower()
            # If page has many short lines (TOC characteristic) and no long paragraphs, likely TOC page
            lines = text.split('\n')
            long_lines = [l for l in lines if len(l.strip()) > 100]
            if len(long_lines) > 5:  # Real content pages should have 5+ long lines
                content_start_page = page_num
                break
        
        # ── Method: Precise search, exclude TOC entries ──
        for keyword in section_keywords:
            if keyword in result:
                continue
            
            keyword_lower = keyword.lower()
            
            # Find all occurrences in complete text
            all_matches = []
            start = 0
            while True:
                pos = full_text.lower().find(keyword_lower, start)
                if pos < 0:
                    break
                all_matches.append(pos)
                start = pos + 1
            
            # Score and filter each match
            best_match = None
            best_score = -1
            
            for match_pos in all_matches:
                # Get the line containing the match
                line_start = full_text.rfind('\n', 0, match_pos) + 1
                line_end = full_text.find('\n', match_pos)
                if line_end < 0:
                    line_end = len(full_text)
                match_line = full_text[line_start:line_end]
                
                # Scoring logic: Is this a real section or a TOC entry?
                score = 0
                
                # Deduct points: This line looks like a TOC entry
                if '...' in match_line:
                    score -= 100  # TOC entry characteristics too obvious
                if re.match(r'^[\d\.]+\s+.+\d+\s*$', match_line.strip()):
                    # Matches "1.4.2 XXX 15" pattern = TOC entry
                    score -= 50
                
                # Add points: This position has real content after
                content_after = full_text[match_pos:min(match_pos + 2000, len(full_text))]
                # Check if subsequent content is actual paragraph (not continued TOC)
                lines_after = content_after.split('\n')
                substantive_lines = [
                    l for l in lines_after 
                    if len(l.strip()) > 50 and '...' not in l
                ]
                if len(substantive_lines) >= 5:
                    score += 50  # Has substantive content after
                
                # Add points: In content section not TOC section
                if match_pos > (toc_end_marker or 0):
                    score += 30
                
                # Deduct points: In TOC section
                if toc_end_marker and match_pos < toc_end_marker:
                    score -= 40
                
                # Record highest-scoring match
                if score > best_score:
                    best_score = score
                    best_match = match_pos
            
            # Extract section using best match
            if best_match is not None and best_score >= 0:  # Must be valid match
                section_start = max(0, best_match - 1500)
                
                # Find next same-level section
                search_from = best_match + len(keyword)
                
                # Find next section with format "1.5 XXX" or "1.4.3 YYY"
                next_section_pattern = re.compile(
                    r'\n\s*(\d+\.\d+(?:\.\d+)*)\s+[A-Z][^\n]{10,}',
                    re.MULTILINE
                )
                
                # Parse current section's numbering level
                current_section_pattern = re.compile(
                    r'\b(\d+\.\d+(?:\.\d+)*)\s+' + re.escape(keyword),
                    re.IGNORECASE
                )
                current_match = current_section_pattern.search(full_text, best_match - 1000)
                current_level = len(current_match.group(1).split('.')) if current_match else 999
                
                section_end = len(full_text)
                for m in next_section_pattern.finditer(full_text, search_from + 100):
                    next_num = m.group(1)
                    next_level = len(next_num.split('.'))
                    # When found same or higher-level section, use as end
                    if next_level <= current_level:
                        section_end = m.start()
                        break
                
                # Limit extraction size
                if section_end - section_start > 35000:
                    section_end = section_start + 35000
                
                extracted = full_text[section_start:section_end].strip()
                
                # Final quality check: Must have sufficient substantive content (can't be pure TOC)
                extracted_lines = extracted.split('\n')
                content_lines = [
                    l for l in extracted_lines 
                    if len(l.strip()) > 50 and '...' not in l
                ]
                
                if len(content_lines) >= 5:  # At least 5 lines of substantive content
                    result[keyword] = extracted
    
    except Exception:
        pass
    
    return result

    # ── Plain text ──
    if mime_type in ("text/plain", "text/markdown"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    # ── Final fallback: Try reading as text ──
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        if len(text.strip()) > 50:
            return text
    except Exception:
        pass

    return ""


async def file_process_task(ctx, file_id: str, task_id: str):
    """File content extraction task."""
    try:
        await update_task_progress(task_id, "Reading file...")

        async with AsyncSessionLocal() as db:
            result = await db.exec(select(TOEFile).where(TOEFile.id == file_id))
            toe_file = result.first()
            if not toe_file:
                await fail_task(task_id, "File record not found")
                return

            toe_file.process_status = "processing"
            db.add(toe_file)
            await db.commit()

        await update_task_progress(task_id, "Extracting file content...")

        extracted_text = ""
        if toe_file.file_type == "document":
            extracted_text = await _extract_document_text(
                toe_file.file_path, toe_file.mime_type
            )
        elif toe_file.file_type == "image":
            # Image file placeholder for now; can integrate AI vision later
            extracted_text = f"[Image file: {toe_file.original_filename}]"
        elif toe_file.file_type == "video":
            extracted_text = f"[Video file: {toe_file.original_filename}]"
        else:
            extracted_text = f"[Other file: {toe_file.original_filename}]"

        # Save extracted result to file
        text_dir = os.path.dirname(toe_file.file_path)
        text_filename = os.path.splitext(toe_file.filename)[0] + ".extracted.txt"
        text_path = os.path.join(text_dir, text_filename)

        with open(text_path, "w", encoding="utf-8") as f:
            f.write(extracted_text)

        # Update file record
        async with AsyncSessionLocal() as db:
            result = await db.exec(select(TOEFile).where(TOEFile.id == file_id))
            toe_file = result.first()
            if toe_file:
                toe_file.process_status = "ready"
                toe_file.extracted_text_path = text_path
                db.add(toe_file)
                await db.commit()

        await finish_task(task_id, f"File processing completed, extracted {len(extracted_text)} characters")
    except Exception as e:
        # Mark file processing as failed
        try:
            async with AsyncSessionLocal() as db:
                result = await db.exec(select(TOEFile).where(TOEFile.id == file_id))
                toe_file = result.first()
                if toe_file:
                    toe_file.process_status = "failed"
                    toe_file.process_error = str(e)
                    db.add(toe_file)
                    await db.commit()
        except Exception:
            pass
        await fail_task(task_id, str(e))


# ── B3-4: ST document parsing task ─────────────────────────────────

async def st_parse_task(ctx, st_reference_id: str, task_id: str, language: str = "en"):
    """ST document parsing task: extract text -> AI structured extraction -> store JSON fields."""
    from datetime import timezone
    try:
        msg_reading = "Reading ST document..."
        await update_task_progress(task_id, msg_reading)
        from app.models.threat import STReference, STReferenceFile
        from app.services.ai_service import AIService
        from app.models.ai_model import AIModel

        async with AsyncSessionLocal() as db:
            # Get ST reference record
            result = await db.exec(select(STReference).where(STReference.id == st_reference_id))
            st_ref = result.first()
            if not st_ref:
                await fail_task(task_id, "ST reference not found")
                return

            st_ref.parse_status = "processing"
            db.add(st_ref)
            await db.commit()

            # Get associated files
            files_result = await db.exec(
                select(STReferenceFile).where(STReferenceFile.st_reference_id == st_reference_id)
            )
            st_files = files_result.all()

            # Get AI service: prioritize is_active, then is_verified
            model_result = await db.exec(
                select(AIModel).where(
                    AIModel.user_id == st_ref.user_id,
                    AIModel.is_active == True,
                    AIModel.deleted_at.is_(None),
                ).limit(1)
            )
            ai_model = model_result.first()
            if not ai_model:
                model_result = await db.exec(
                    select(AIModel).where(
                        AIModel.user_id == st_ref.user_id,
                        AIModel.is_verified == True,
                        AIModel.deleted_at.is_(None),
                    ).limit(1)
                )
                ai_model = model_result.first()

        await update_task_progress(task_id, "Extracting document text...")

        # Extract text from all files
        all_text = ""
        for st_file in st_files:
            text = await _extract_document_text(st_file.file_path, st_file.mime_type)
            all_text += text + "\n\n"

        if not all_text.strip():
            msg_no_text = "Unable to extract document text"
            async with AsyncSessionLocal() as db:
                result = await db.exec(select(STReference).where(STReference.id == st_reference_id))
                st_ref = result.first()
                if st_ref:
                    st_ref.parse_status = "failed"
                    st_ref.parse_error = msg_no_text
                    db.add(st_ref)
                    await db.commit()
            await fail_task(task_id, msg_no_text)
            return

        extracted = {}
        if ai_model:
            from app.core.security import decrypt_api_key
            import re
            ai = AIService(
                api_base=ai_model.api_base,
                api_key_encrypted=ai_model.api_key_encrypted,
                model_name=ai_model.model_name,
                timeout_seconds=ai_model.timeout_seconds,
            )

            # ── TOC-based section extraction for PDFs ──────────────────────────
            # Try to use PDF TOC (Table of Contents) with page ranges for accuracy
            toc_sections = {}
            section_keywords = [
                # Core ST/PP sections
                "Security Problem Definition",
                "Security Objectives", 
                "Security Functional Requirements",
                "Security Requirements",
                "Threats",
                "Assumptions",
                "OSPs",
                # TOE description sections
                "TOE Description",
                "TOE Overview",
                "TOE Summary",
                "TOE Usage",
                "Major Security Features",
                "Physical Scope",
                "Logical Scope",
                # Dependencies and environment
                "Required Non-TOE Hardware",
                "Required Non-TOE Software",
                "Required Non-TOE Firmware",
                "Required Non-TOE Hardware/Software/Firmware",
                "Environmental Assumptions",
                # Other common ST/PP sections
                "Conformance Claims",
                "Security Assurance Requirements",
                "Protection Profile",
                "Rationale",
                "Evaluation Assurance Levels"
            ]
            
            # Check if we have a PDF file
            if st_files and st_files[0].mime_type == "application/pdf":
                try:
                    toc_sections = _extract_pdf_toc_and_page_content(st_files[0].file_path, section_keywords)
                except Exception:
                    pass  # Fallback to pattern-based extraction if TOC extraction fails

            # ── Define fallback pattern-based section extraction ──────────────────────────
            # ST/PP documents can be 79K+ chars. Different data lives in
            # different chapters. Extract targeted sections for each AI call.

            def _extract_st_section(full_text: str, chapter_pattern, next_pattern, marker_re, max_chars: int = 20000) -> str:
                """Extract a chapter section from ST/PP document by heading patterns."""
                # Strategy 1: Match chapter heading (skip TOC entries with ...)
                for m_start in chapter_pattern.finditer(full_text):
                    line_end = full_text.find('\n', m_start.end())
                    line_after = full_text[m_start.end():line_end if line_end > 0 else m_start.end() + 200]
                    if '...' in line_after or re.match(r'\s*\d+\s*$', line_after.strip()):
                        continue
                    start = m_start.start()
                    end = min(start + max_chars, len(full_text))
                    for m_end in next_pattern.finditer(full_text, start + 100):
                        end_line = full_text.find('\n', m_end.end())
                        end_after = full_text[m_end.end():end_line if end_line > 0 else m_end.end() + 200]
                        if '...' in end_after:
                            continue
                        end = m_end.start()
                        break
                    section = full_text[start:end].strip()
                    if len(section) > 300:
                        return section[:max_chars]

                # Strategy 2: Find code markers (e.g. T.XXX, O.XXX) and extract context
                if marker_re:
                    markers = list(marker_re.finditer(full_text))
                    if markers:
                        first_pos = max(0, markers[0].start() - 500)
                        last_pos = min(len(full_text), markers[-1].end() + 2000)
                        section = full_text[first_pos:last_pos].strip()
                        if len(section) > 300:
                            return section[:max_chars]

                # Strategy 3: Fallback — full text truncated
                return full_text[:max_chars]

            # ── Call 1: Threats / Assumptions / OSPs (SPD chapter) ──
            msg_extracting_spd = "AI extracting threats/assumptions/OSPs (1/3)..."
            await update_task_progress(task_id, msg_extracting_spd)

            # Try to use TOC-extracted SPD section, fallback to pattern-based
            if "Security Problem Definition" in toc_sections:
                spd_text = toc_sections["Security Problem Definition"][:25000]
            else:
                spd_text = _extract_st_section(
                    all_text,
                    chapter_pattern=re.compile(r'(?:^|\n)\s*\d*\.?\d*\s*Security\s+Problem\s+Definition', re.IGNORECASE),
                    next_pattern=re.compile(r'(?:^|\n)\s*\d+\.?\d*\s*Security\s+(?:Objectives|Requirements|Functional)', re.IGNORECASE),
                    marker_re=re.compile(r'(?:^|\s)(T\.[A-Z_]{2,}|A\.[A-Z_]{2,}|P\.[A-Z_]{2,})'),
                )
            prompt_spd = f"""You are a CC (Common Criteria) evaluation expert. Extract threats, assumptions and OSPs from this Security Target document.

--- DOCUMENT TEXT (Security Problem Definition section) ---
{spd_text}
--- END ---

Extract ONLY items explicitly present in the text. Keep the EXACT code and description from the document.
Preserve the original document language exactly. Do NOT translate, rewrite, or paraphrase extracted text.
Return JSON:
{{
  "threats": [{{"code": "T.XXX", "description": "threat description"}}],
  "assumptions": [{{"code": "A.XXX", "description": "assumption description"}}],
  "osps": [{{"code": "P.XXX", "description": "OSP description"}}]
}}"""
            try:
                spd_result = await ai.chat_json(prompt_spd, max_tokens=8192)
                extracted.update(spd_result or {})
            except Exception as e:
                                extracted["parse_note_spd"] = f"Extraction failed: {str(e)[:200]}"

            # ── Call 2: Security Objectives ──
            await update_task_progress(task_id, "AI extracting security objectives (2/3)...")

            # Try to use TOC-extracted SO section, fallback to pattern-based
            if "Security Objectives" in toc_sections:
                obj_text = toc_sections["Security Objectives"][:25000]
            else:
                obj_text = _extract_st_section(
                    all_text,
                    chapter_pattern=re.compile(r'(?:^|\n)\s*\d*\.?\d*\s*Security\s+Objectives', re.IGNORECASE),
                    next_pattern=re.compile(r'(?:^|\n)\s*\d+\.?\d*\s*(?:Extended\s+Components|Security\s+Requirements|Security\s+Functional)', re.IGNORECASE),
                    marker_re=re.compile(r'(?:^|\s)(O\.[A-Z_]{2,}|OE\.[A-Z_]{2,})'),
                )
            prompt_obj = f"""You are a CC (Common Criteria) evaluation expert. Extract security objectives from this Security Target document.

--- DOCUMENT TEXT (Security Objectives section) ---
{obj_text}
--- END ---

Extract ONLY items explicitly present in the text. Keep the EXACT code and description.
Preserve the original document language exactly. Do NOT translate, rewrite, or paraphrase extracted text.
Return JSON:
{{
  "objectives": [{{"code": "O.XXX", "type": "O", "description": "objective description"}}]
}}
Note: type is "O" for TOE objectives, "OE" for environment objectives."""
            try:
                obj_result = await ai.chat_json(prompt_obj, max_tokens=8192)
                extracted.update(obj_result or {})
            except Exception as e:
                extracted["parse_note_obj"] = f"Extraction failed: {str(e)[:200]}"

            # ── Call 3: SFRs + Assets ──
            await update_task_progress(task_id, "AI extracting SFRs and assets (3/3)...")

            # Try to use TOC-extracted SFR section, fallback to pattern-based
            if "Security Functional Requirements" in toc_sections:
                sfr_text = toc_sections["Security Functional Requirements"][:25000]
            elif "Security Requirements" in toc_sections:
                sfr_text = toc_sections["Security Requirements"][:25000]
            else:
                sfr_text = _extract_st_section(
                    all_text,
                    chapter_pattern=re.compile(r'(?:^|\n)\s*\d*\.?\d*\s*Security\s+(?:Functional\s+)?Requirements', re.IGNORECASE),
                    next_pattern=re.compile(r'(?:^|\n)\s*\d+\.?\d*\s*(?:Security\s+Assurance|TOE\s+Summary|Rationale)', re.IGNORECASE),
                    marker_re=re.compile(r'(?:^|\s)(F[A-Z]{2}_[A-Z]{3}(?:\.\d+)?)'),
                )
            # For assets, also check TOE description section
            asset_text = _extract_st_section(
                all_text,
                chapter_pattern=re.compile(r'(?:^|\n)\s*\d*\.?\d*\s*(?:TOE\s+Description|TOE\s+Overview|Product\s+Description)', re.IGNORECASE),
                next_pattern=re.compile(r'(?:^|\n)\s*\d+\.?\d*\s*(?:Security\s+Problem|Conformance|Security\s+Objectives)', re.IGNORECASE),
                marker_re=None,
            )
            combined_sfr_asset = sfr_text
            if asset_text != sfr_text:
                combined_sfr_asset = sfr_text + "\n\n--- Additional context (TOE Description) ---\n" + asset_text[:10000]

            prompt_sfr = f"""You are a CC (Common Criteria) evaluation expert. Extract SFRs and assets from this Security Target document.

--- DOCUMENT TEXT (Requirements & TOE Description sections) ---
{combined_sfr_asset[:25000]}
--- END ---

Extract ONLY items explicitly present in the text. Keep the EXACT identifiers and descriptions.
Return JSON:
{{
  "sfrs": [{{"sfr_id": "FDP_ACC.1", "description": "SFR description"}}],
  "assets": [{{"name": "asset name", "description": "asset description"}}]
}}"""
            try:
                sfr_result = await ai.chat_json(prompt_sfr, max_tokens=8192)
                extracted.update(sfr_result or {})
            except Exception as e:
                extracted["parse_note_sfr"] = f"Extraction failed: {str(e)[:200]}"
        else:
            extracted = {"parse_note": "No AI model configured, skipping structured extraction"}

        import json
        async with AsyncSessionLocal() as db:
            result = await db.exec(select(STReference).where(STReference.id == st_reference_id))
            st_ref = result.first()
            if st_ref:
                st_ref.parse_status = "ready"
                st_ref.threats_extracted = json.dumps(extracted.get("threats", []), ensure_ascii=False)
                st_ref.objectives_extracted = json.dumps(
                    extracted.get("objectives", []), ensure_ascii=False
                )
                st_ref.sfr_extracted = json.dumps(extracted.get("sfrs", []), ensure_ascii=False)
                st_ref.assets_extracted = json.dumps(extracted.get("assets", []), ensure_ascii=False)
                st_ref.parsed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                db.add(st_ref)
                await db.commit()

        await finish_task(task_id, "ST document parsing completed")
    except Exception as e:
        try:
            from app.models.threat import STReference
            async with AsyncSessionLocal() as db:
                result = await db.exec(select(STReference).where(STReference.id == st_reference_id))
                st_ref = result.first()
                if st_ref:
                    st_ref.parse_status = "failed"
                    st_ref.parse_error = str(e)
                    db.add(st_ref)
                    await db.commit()
        except Exception:
            pass
        await fail_task(task_id, str(e))


# ── B3-9 / B3-10: Threat scanning task ───────────────────────────────

async def threat_scan_task(ctx, toe_id: str, mode: str, task_id: str, language: str = "en"):
    """Threat scanning (full or incremental), updating progress in 4 stages."""
    try:
        language = (language or "en").lower()

        await update_task_progress(task_id, "Stage 1/4: Reading TOE information...")

        from app.models.toe import TOE, TOEFile, TOEAsset
        from app.models.threat import Threat
        from app.models.ai_model import AIModel
        from app.services.ai_service import AIService

        async with AsyncSessionLocal() as db:
            toe = (await db.exec(select(TOE).where(TOE.id == toe_id))).first()
            if not toe:
                await fail_task(task_id, "TOE not found")
                return

            assets = (await db.exec(
                select(TOEAsset).where(
                    TOEAsset.toe_id == toe_id,
                    TOEAsset.deleted_at.is_(None),
                )
            )).all()

            ready_files = (await db.exec(
                select(TOEFile).where(
                    TOEFile.toe_id == toe_id,
                    TOEFile.process_status == "ready",
                    TOEFile.deleted_at.is_(None),
                )
            )).all()

            existing_threats = (await db.exec(
                select(Threat).where(
                    Threat.toe_id == toe_id,
                    Threat.deleted_at.is_(None),
                )
            )).all()

            ai_model = (await db.exec(
                select(AIModel).where(
                    AIModel.user_id == toe.user_id,
                    AIModel.is_active == True,
                    AIModel.deleted_at.is_(None),
                ).limit(1)
            )).first()
            if not ai_model:
                ai_model = (await db.exec(
                    select(AIModel).where(
                        AIModel.user_id == toe.user_id,
                        AIModel.is_verified == True,
                        AIModel.deleted_at.is_(None),
                    ).limit(1)
                )).first()

        if not ai_model:
            await fail_task(
                task_id,
                "未找到可用的 AI 模型。请先配置并验证 AI 模型。"
                if language == "zh"
                else "No available AI model found. Please configure and verify an AI model first.",
            )
            return

        await update_task_progress(task_id, "Stage 2/4: Reading document content...")

        file_texts: list[str] = []
        for toe_file in ready_files[:5]:
            if toe_file.extracted_text_path and os.path.exists(toe_file.extracted_text_path):
                with open(toe_file.extracted_text_path, "r", encoding="utf-8", errors="ignore") as handle:
                    text = handle.read()[:3000]
                title = f"[Document: {toe_file.original_filename}]"
                file_texts.append(f"{title}\n{text}")

            await update_task_progress(task_id, "Stage 3/4: AI identifying threats...")

        ai = AIService(
            api_base=ai_model.api_base,
            api_key_encrypted=ai_model.api_key_encrypted,
            model_name=ai_model.model_name,
            timeout_seconds=ai_model.timeout_seconds,
        )

        if assets:
            asset_lines = [
                f"  - {asset.name} (Type: {asset.asset_type}, Importance: {asset.importance}/5): {asset.description or 'No description'}"
                for asset in assets
            ]
            asset_summary = "TOE asset list:\n" + "\n".join(asset_lines)
        else:
            asset_summary = "TOE asset list: not defined"

        existing_summary = ""
        if mode == "incremental" and existing_threats:
            existing_summary = "Existing threats (do not duplicate; identify only new ones):\n" + "\n".join(
                f"  - {threat.code}: {threat.adverse_action or threat.threat_agent or ''}"
                for threat in existing_threats
            )

        file_context = "\n\n".join(file_texts) if file_texts else "No processed documents"

        toe_sections: list[str] = []
        if toe.brief_intro:
            toe_sections.append(f"Summary: {toe.brief_intro}")
        if toe.toe_type_desc:
            toe_sections.append(f"Product type description: {toe.toe_type_desc}")
        if toe.toe_usage:
            toe_sections.append(f"Usage scenarios: {toe.toe_usage}")
        if toe.major_security_features:
            toe_sections.append(f"Major security features: {toe.major_security_features}")
        if toe.physical_scope:
            toe_sections.append(f"Physical scope: {toe.physical_scope}")
        if toe.logical_scope:
            toe_sections.append(f"Logical scope: {toe.logical_scope}")
        if toe.hw_interfaces:
            toe_sections.append(f"Hardware interfaces: {toe.hw_interfaces}")
        if toe.sw_interfaces:
            toe_sections.append(f"Software interfaces: {toe.sw_interfaces}")
        if toe.required_non_toe_hw_sw_fw:
            toe_sections.append(f"Required non-TOE components: {toe.required_non_toe_hw_sw_fw}")
        if toe.description and not toe.toe_type_desc:
            toe_sections.append(f"Description: {(toe.description or '')[:500]}")
        if toe.boundary and not toe.logical_scope:
            toe_sections.append(f"Boundary: {(toe.boundary or '')[:300]}")
        if toe.operational_env:
            toe_sections.append(f"Operational environment: {(toe.operational_env or '')[:300]}")

        toe_detail = "\n".join(toe_sections) if toe_sections else "No detailed description"
        output_language = "Chinese" if language == "zh" else "English"

        prompt = f"""You are a Common Criteria security expert. Perform a comprehensive threat analysis for the TOE below.

═══════════════════════════════════════
TOE basic information:
- Name: {toe.name}
- Version: {toe.version or 'Not specified'}
- Type: {toe.toe_type}

{toe_detail}

═══════════════════════════════════════
{asset_summary}

═══════════════════════════════════════
Relevant document content:
{file_context[:4000]}

═══════════════════════════════════════
{existing_summary}

═══════════════════════════════════════
Task: {"Identify only genuinely new threats that are not already covered above. Do not repeat existing items." if mode == "incremental" and existing_threats else "Identify all potential security threats faced by this TOE."}

Analysis points:
1. Analyze the attack surface based on TOE functions, interfaces, and usage scenarios.
2. Identify threats for each important asset.
3. Consider both external attackers and malicious insiders.
4. Cover common CC threat categories such as unauthorized access, tampering, denial of service, and information disclosure.

Return JSON in this format:
{{
  "threats": [
    {{
      "code": "T.UNAUTH_ACCESS",
            "threat_definition": "Threat definition written in {output_language}.",
      "likelihood": "high",
      "impact": "high",
            "ai_rationale": "Reasoning written in {output_language}."
    }}
  ]
}}

Requirements:
- Identify {"3-8 new" if mode == "incremental" and existing_threats else "8-15"} threats
- Code format: T.UPPERCASE_ENGLISH (for example, T.UNAUTH_ACCESS)
- threat_definition must be a complete natural-language paragraph including threat actor, adverse action, and affected asset
- likelihood / impact values: low / medium / high
- All descriptions must be in {output_language} and code must be in English"""

        result = await ai.chat_json(prompt)
        threats_data = result.get("threats", []) if isinstance(result, dict) else []

        await update_task_progress(
            task_id,
            f"Stage 4/4: Writing {len(threats_data)} candidate threats...",
        )

        from app.routers.threats import _unique_code, calc_risk_level, _infer_assets_for_threat, _replace_threat_asset_links

        added = 0
        async with AsyncSessionLocal() as db:
            for threat_data in threats_data:
                code = (threat_data.get("code") or "").strip().upper()
                if not code:
                    continue
                if not code.startswith("T."):
                    code = "T." + code
                code = await _unique_code(Threat, toe_id, code, db)

                likelihood = threat_data.get("likelihood", "medium")
                impact = threat_data.get("impact", "medium")

                threat = Threat(
                    toe_id=toe_id,
                    code=code,
                    adverse_action=threat_data.get("threat_definition"),
                    likelihood=likelihood,
                    impact=impact,
                    risk_level=calc_risk_level(likelihood, impact),
                    review_status="pending",
                    ai_rationale=threat_data.get("ai_rationale"),
                )
                db.add(threat)
                await db.flush()

                linked_assets = await _infer_assets_for_threat(
                    toe_id,
                    {"adverse_action": threat_data.get("threat_definition")},
                    db,
                    threat,
                )
                await _replace_threat_asset_links(threat.id, linked_assets, db)
                added += 1

            await db.commit()

        summary = (
            f"Incremental scan completed, added {added} candidate threats"
            if mode == "incremental" and added > 0
            else (
                "Incremental scan completed, no new threats found"
                if mode == "incremental"
                else f"Full scan completed, identified {added} candidate threats"
            )
        )
        await finish_task(task_id, summary)

    except Exception as e:
        await fail_task(task_id, str(e))


async def threat_import_task(ctx, toe_id: str, task_id: str):
    """Extract threats, assumptions, and OSPs from the TOE's ST/PP documents and write them to the database."""
    try:
        await update_task_progress(task_id, "threat_import.stage_1")

        from app.models.toe import TOE, TOEFile
        from app.models.threat import Threat, Assumption, OSP
        from app.models.ai_model import AIModel
        from app.services.ai_service import AIService

        async with AsyncSessionLocal() as db:
            # Read TOE
            toe_result = await db.exec(select(TOE).where(TOE.id == toe_id))
            toe = toe_result.first()
            if not toe:
                await fail_task(task_id, "TOE not found")
                return

            # Read ST/PP documents (already processed)
            files_result = await db.exec(
                select(TOEFile).where(
                    TOEFile.toe_id == toe_id,
                    TOEFile.file_category == "st_pp",
                    TOEFile.process_status == "ready",
                    TOEFile.deleted_at.is_(None),
                )
            )
            st_pp_files = files_result.all()
            if not st_pp_files:
                await fail_task(task_id, "No ST/PP documents are available")
                return

            # Read existing entries (for deduplication)
            t_res = await db.exec(select(Threat).where(Threat.toe_id == toe_id, Threat.deleted_at.is_(None)))
            existing_threat_codes = {t.code.upper() for t in t_res.all()}

            a_res = await db.exec(select(Assumption).where(Assumption.toe_id == toe_id, Assumption.deleted_at.is_(None)))
            existing_assumption_codes = {a.code.upper() for a in a_res.all()}

            o_res = await db.exec(select(OSP).where(OSP.toe_id == toe_id, OSP.deleted_at.is_(None)))
            existing_osp_codes = {o.code.upper() for o in o_res.all()}

            # Get AI service: prioritize is_active, then is_verified
            model_result = await db.exec(
                select(AIModel).where(
                    AIModel.user_id == toe.user_id,
                    AIModel.is_active == True,
                    AIModel.deleted_at.is_(None),
                ).limit(1)
            )
            ai_model = model_result.first()
            if not ai_model:
                model_result = await db.exec(
                    select(AIModel).where(
                        AIModel.user_id == toe.user_id,
                        AIModel.is_verified == True,
                        AIModel.deleted_at.is_(None),
                    ).limit(1)
                )
                ai_model = model_result.first()

        if not ai_model:
            await fail_task(task_id, "No available AI model found. Please configure and verify an AI model first.")
            return

        await update_task_progress(task_id, "threat_import.stage_2")

        # ── Intelligently extract SPD-related sections ──
        # Threats/Assumptions/OSP in ST/PP usually in "Security Problem Definition" section
        # Not at document start, so can't just read first N characters
        import re

        def _extract_spd_sections(full_text: str, max_chars: int = 20000) -> str:
            """Extract passages related to Threats / Assumptions / OSP from the full ST/PP text."""
            # Strategy 1: Locate by CC ST standard section title "Security Problem Definition"
            # Skip TOC entries (lines with ...)
            spd_pattern = re.compile(
                r'(?:^|\n)\s*\d*\.?\d*\s*Security\s+Problem\s+Definition',
                re.IGNORECASE
            )
            next_chapter = re.compile(
                r'(?:^|\n)\s*\d+\.?\d*\s*Security\s+(?:Objectives|Requirements|Functional)',
                re.IGNORECASE
            )
            for m_start in spd_pattern.finditer(full_text):
                # Skip TOC entries (followed by .... or page number)
                line_end = full_text.find('\n', m_start.end())
                line_after = full_text[m_start.end():line_end if line_end > 0 else m_start.end() + 200]
                if '...' in line_after or re.match(r'\s*\d+\s*$', line_after.strip()):
                    continue
                start = m_start.start()
                # Find next section title (also skip TOC entries)
                end = min(start + max_chars, len(full_text))
                for m_end in next_chapter.finditer(full_text, start + 100):
                    end_line = full_text.find('\n', m_end.end())
                    end_after = full_text[m_end.end():end_line if end_line > 0 else m_end.end() + 200]
                    if '...' in end_after:
                        continue
                    end = m_end.start()
                    break
                section = full_text[start:end].strip()
                if len(section) > 500:
                    return section[:max_chars]

            # Strategy 2: Keyword window method - find all T.xxx / A.xxx / P.xxx occurrences, get context
            spd_markers = list(re.finditer(
                r'(?:^|\s)(T\.[A-Z_]{2,}|A\.[A-Z_]{2,}|P\.[A-Z_]{2,})',
                full_text
            ))
            if spd_markers:
                first_pos = max(0, spd_markers[0].start() - 500)
                last_pos = min(len(full_text), spd_markers[-1].end() + 2000)
                section = full_text[first_pos:last_pos].strip()
                if len(section) > 500:
                    return section[:max_chars]

            # Strategy 3: Fallback - use full text (truncated)
            return full_text[:max_chars]

        file_texts = []
        for f in st_pp_files:
            if f.extracted_text_path and os.path.exists(f.extracted_text_path):
                with open(f.extracted_text_path, "r", encoding="utf-8", errors="ignore") as fp:
                    full_text = fp.read()
                section = _extract_spd_sections(full_text)
                file_texts.append(f"【{f.original_filename}】\n{section}")

        if not file_texts:
            await fail_task(task_id, "Document content is empty and cannot be extracted. Confirm parsing completed successfully.")
            return

        await update_task_progress(task_id, "threat_import.stage_3")

        import_timeout = await _get_import_timeout(getattr(ai_model, "timeout_seconds", None))

        ai = AIService(
            api_base=ai_model.api_base,
            api_key_encrypted=ai_model.api_key_encrypted,
            model_name=ai_model.model_name,
            timeout_seconds=import_timeout,
        )
        doc_content = "\n\n".join(file_texts)[:40000]
        source_ref = ", ".join(f.original_filename for f in st_pp_files)

        prompt = f"""You are a CC (Common Criteria) security expert. Extract ALL threats, assumptions and OSPs from the "Security Problem Definition" section of the following ST/PP document(s).

DOCUMENT CONTENT:
{doc_content}

INSTRUCTIONS:
- Extract EVERY item with code prefix T. (threats), A. (assumptions), P. (OSPs) found in the document
- Keep the EXACT code as written in the document (e.g. T.UNAUTHORISED_ACCESS, A.TRUSTED_USERS, P.FIRMWARE_RELEASE)
- Keep the EXACT definition text from the document — do NOT rephrase, summarize, or add your own words
- If a definition spans multiple lines/paragraphs in the document, combine them into one string
- Do NOT invent items that are not present in the document

Return JSON:
{{
  "threats": [
    {{"code": "T.EXAMPLE", "definition": "exact definition from document..."}}
  ],
  "assumptions": [
    {{"code": "A.EXAMPLE", "definition": "exact definition from document..."}}
  ],
  "osps": [
    {{"code": "P.EXAMPLE", "definition": "exact definition from document..."}}
  ]
}}"""

        result = await ai.chat_json(prompt, max_tokens=8192)
        threats_data = result.get("threats", [])
        assumptions_data = result.get("assumptions", [])
        osps_data = result.get("osps", [])

        # Write to database
        from app.routers.threats import _unique_code, calc_risk_level, _infer_assets_for_threat, _replace_threat_asset_links
        added_threats = added_assumptions = added_osps = 0

        async with AsyncSessionLocal() as db:
            # Write threats
            for td in threats_data:
                code = (td.get("code") or "").strip().upper()
                if not code:
                    continue
                if not code.startswith("T."):
                    code = "T." + code
                if code in existing_threat_codes:
                    continue
                code = await _unique_code(Threat, toe_id, code, db)
                threat = Threat(
                    toe_id=toe_id,
                    code=code,
                    adverse_action=td.get("definition"),
                    review_status="pending",
                    ai_rationale="Extracted from ST/PP documents",
                    ai_source_ref=source_ref,
                )
                db.add(threat)
                await db.flush()
                linked_assets = await _infer_assets_for_threat(
                    toe_id,
                    {"adverse_action": td.get("definition")},
                    db,
                    threat,
                )
                await _replace_threat_asset_links(threat.id, linked_assets, db)
                existing_threat_codes.add(code)
                added_threats += 1

            # Write assumptions
            for ad in assumptions_data:
                code = (ad.get("code") or "").strip().upper()
                if not code:
                    continue
                if not code.startswith("A."):
                    code = "A." + code
                if code in existing_assumption_codes:
                    continue
                code = await _unique_code(Assumption, toe_id, code, db)
                db.add(Assumption(
                    toe_id=toe_id,
                    code=code,
                    description=ad.get("definition"),
                    review_status="pending",
                    ai_generated=True,
                ))
                existing_assumption_codes.add(code)
                added_assumptions += 1

            # Write OSPs
            for od in osps_data:
                code = (od.get("code") or "").strip().upper()
                if not code:
                    continue
                if not code.startswith("P."):
                    code = "P." + code
                if code in existing_osp_codes:
                    continue
                code = await _unique_code(OSP, toe_id, code, db)
                db.add(OSP(
                    toe_id=toe_id,
                    code=code,
                    description=od.get("definition"),
                    review_status="pending",
                    ai_generated=True,
                ))
                existing_osp_codes.add(code)
                added_osps += 1

            await db.commit()

        await finish_task(
            task_id,
            f"threat_import.done|{len(threats_data)}|{len(assumptions_data)}|{len(osps_data)}|{added_threats}|{added_assumptions}|{added_osps}"
        )

    except Exception as e:
        await fail_task(task_id, str(e))


async def objective_import_task(ctx, toe_id: str, task_id: str):
    """Import security objectives and SFRs from TOE ST/PP documents in stages and batch-create mappings."""
    try:
        await update_task_progress(task_id, "objective_import.stage_1.scan")

        import re
        from app.models.toe import TOE, TOEFile
        from app.models.threat import Threat, Assumption, OSP
        from app.models.security import (
            SecurityObjective,
            SFR,
            SFRLibrary,
            ObjectiveSFR,
            ThreatObjective,
            AssumptionObjective,
            OSPObjective,
        )
        from app.models.ai_model import AIModel
        from app.services.ai_service import AIService

        async with AsyncSessionLocal() as db:
            toe_result = await db.exec(select(TOE).where(TOE.id == toe_id))
            toe = toe_result.first()
            if not toe:
                await fail_task(task_id, "TOE not found")
                return

            files_result = await db.exec(
                select(TOEFile).where(
                    TOEFile.toe_id == toe_id,
                    TOEFile.file_category == "st_pp",
                    TOEFile.process_status == "ready",
                    TOEFile.deleted_at.is_(None),
                )
            )
            st_pp_files = files_result.all()
            if not st_pp_files:
                await fail_task(task_id, "No ST/PP documents are available")
                return

            objective_res = await db.exec(
                select(SecurityObjective).where(
                    SecurityObjective.toe_id == toe_id,
                    SecurityObjective.deleted_at.is_(None),
                )
            )
            existing_objectives = objective_res.all()

            sfr_res = await db.exec(
                select(SFR).where(
                    SFR.toe_id == toe_id,
                    SFR.deleted_at.is_(None),
                )
            )
            existing_sfrs = sfr_res.all()

            library_res = await db.exec(select(SFRLibrary).order_by(SFRLibrary.sfr_component))
            library_items = library_res.all()

            threats = (await db.exec(
                select(Threat).where(Threat.toe_id == toe_id, Threat.deleted_at.is_(None))
            )).all()
            assumptions = (await db.exec(
                select(Assumption).where(Assumption.toe_id == toe_id, Assumption.deleted_at.is_(None))
            )).all()
            osps = (await db.exec(
                select(OSP).where(OSP.toe_id == toe_id, OSP.deleted_at.is_(None))
            )).all()

            model_result = await db.exec(
                select(AIModel).where(
                    AIModel.user_id == toe.user_id,
                    AIModel.is_active == True,
                    AIModel.deleted_at.is_(None),
                ).limit(1)
            )
            ai_model = model_result.first()
            if not ai_model:
                model_result = await db.exec(
                    select(AIModel).where(
                        AIModel.user_id == toe.user_id,
                        AIModel.is_verified == True,
                        AIModel.deleted_at.is_(None),
                    ).limit(1)
                )
                ai_model = model_result.first()

        if not ai_model:
            await fail_task(task_id, "No available AI model found. Please configure and verify an AI model first.")
            return

        def _extract_st_section(full_text: str, chapter_pattern, next_pattern, marker_re, max_chars: int = 22000) -> str:
            for m_start in chapter_pattern.finditer(full_text):
                line_end = full_text.find("\n", m_start.end())
                line_after = full_text[m_start.end():line_end if line_end > 0 else m_start.end() + 200]
                if "..." in line_after or re.match(r"\s*\d+\s*$", line_after.strip()):
                    continue
                start = m_start.start()
                end = min(start + max_chars, len(full_text))
                for m_end in next_pattern.finditer(full_text, start + 100):
                    end_line = full_text.find("\n", m_end.end())
                    end_after = full_text[m_end.end():end_line if end_line > 0 else m_end.end() + 200]
                    if "..." in end_after:
                        continue
                    end = m_end.start()
                    break
                section = full_text[start:end].strip()
                if len(section) > 300:
                    return section[:max_chars]

            markers = list(marker_re.finditer(full_text)) if marker_re else []
            if markers:
                first_pos = max(0, markers[0].start() - 500)
                last_pos = min(len(full_text), markers[-1].end() + 2500)
                section = full_text[first_pos:last_pos].strip()
                if len(section) > 300:
                    return section[:max_chars]

            return full_text[:max_chars]

        def _build_sfr_batch_context(blocks: list[str], sfr_codes: list[str], max_chars: int = 18000) -> str:
            snippets: list[str] = []
            for block in blocks:
                upper_block = block.upper()
                for sfr_code in sfr_codes:
                    start = 0
                    while True:
                        index = upper_block.find(sfr_code.upper(), start)
                        if index < 0:
                            break
                        left = max(0, index - 1000)
                        right = min(len(block), index + 2500)
                        snippets.append(block[left:right])
                        start = index + len(sfr_code)
                        if len("\n\n".join(snippets)) >= max_chars:
                            return "\n\n---\n\n".join(snippets)[:max_chars]
            if not snippets:
                return "\n\n".join(blocks)[:max_chars]
            return "\n\n---\n\n".join(snippets)[:max_chars]

        def _chunked(items: list[str], batch_size: int) -> list[list[str]]:
            return [items[index:index + batch_size] for index in range(0, len(items), batch_size)]

        objective_context_blocks: list[str] = []
        sfr_context_blocks: list[str] = []
        source_ref = ", ".join(file.original_filename for file in st_pp_files)

        for file_index, file in enumerate(st_pp_files, start=1):
            await update_task_progress(task_id, f"objective_import.stage_1.extract|{file_index}|{len(st_pp_files)}")
            if file.extracted_text_path and os.path.exists(file.extracted_text_path):
                with open(file.extracted_text_path, "r", encoding="utf-8", errors="ignore") as fp:
                    full_text = fp.read()
            else:
                full_text = await _extract_document_text(file.file_path, file.mime_type)

            if not full_text.strip():
                continue

            spd_text = _extract_st_section(
                full_text,
                chapter_pattern=re.compile(r'(?:^|\n)\s*\d*\.?\d*\s*Security\s+Problem\s+Definition', re.IGNORECASE),
                next_pattern=re.compile(r'(?:^|\n)\s*\d+\.?\d*\s*Security\s+Objectives', re.IGNORECASE),
                marker_re=re.compile(r'(?:^|\s)(T\.[A-Z_]{2,}|A\.[A-Z_]{2,}|P\.[A-Z_]{2,})'),
            )
            objective_text = _extract_st_section(
                full_text,
                chapter_pattern=re.compile(r'(?:^|\n)\s*\d*\.?\d*\s*Security\s+Objectives', re.IGNORECASE),
                next_pattern=re.compile(r'(?:^|\n)\s*\d+\.?\d*\s*(?:Extended\s+Components|Security\s+Requirements|Security\s+Functional|Security\s+Assurance)', re.IGNORECASE),
                marker_re=re.compile(r'(?:^|\s)(O\.[A-Z_]{2,}|OE\.[A-Z_]{2,})'),
            )
            sfr_text = _extract_st_section(
                full_text,
                chapter_pattern=re.compile(r'(?:^|\n)\s*\d*\.?\d*\s*Security\s+(?:Functional\s+)?Requirements', re.IGNORECASE),
                next_pattern=re.compile(r'(?:^|\n)\s*\d+\.?\d*\s*(?:Security\s+Assurance|TOE\s+Summary|Rationale)', re.IGNORECASE),
                marker_re=re.compile(r'\b(F[A-Z]{2}_[A-Z]{3}\.\d+(?:/[A-Z0-9_-]+)?)\b', re.IGNORECASE),
            )

            objective_context_blocks.append(
                f"【{file.original_filename}】\n\n[Security Problem Definition]\n{spd_text}\n\n[Security Objectives]\n{objective_text}"
            )
            sfr_context_blocks.append(
                f"【{file.original_filename}】\n\n[Security Requirements]\n{sfr_text}"
            )

        if not objective_context_blocks:
            await fail_task(task_id, "Document content is empty and cannot be extracted. Confirm parsing completed successfully.")
            return

        import_timeout = await _get_import_timeout(getattr(ai_model, "timeout_seconds", None))
        ai = AIService(
            api_base=ai_model.api_base,
            api_key_encrypted=ai_model.api_key_encrypted,
            model_name=ai_model.model_name,
            timeout_seconds=import_timeout,
        )

        await update_task_progress(task_id, "objective_import.stage_2.prepare")

        objective_doc_content = "\n\n".join(objective_context_blocks)[:42000]
        objective_prompt = f"""You are a CC (Common Criteria) security expert. Extract security objectives from the provided ST/PP document content.

DOCUMENT CONTENT:
{objective_doc_content}

INSTRUCTIONS:
- Extract every Security Objective code exactly as written.
- Keep the exact objective definition text from the document; do not summarize.
- Preserve the original document language exactly. Do not translate, rewrite, or paraphrase the extracted definition.
- Determine obj_type as O or OE based on the code and the document.
- For each objective, include related security problem codes (T./A./P.) only when the document or immediate rationale makes the linkage clear.
- Do not invent codes not present in the document.

Return JSON:
{{
    "objectives": [
        {{
            "code": "O.EXAMPLE",
            "obj_type": "O",
            "description": "exact objective definition from document",
            "source_codes": ["T.EXAMPLE", "P.EXAMPLE"]
        }}
    ]
}}"""

        await update_task_progress(task_id, "objective_import.stage_2.ai")
        objective_result = await ai.chat_json(objective_prompt, max_tokens=8192)
        objectives_data = objective_result.get("objectives", []) if isinstance(objective_result, dict) else []

        existing_objective_by_code = {item.code.strip().upper(): item for item in existing_objectives}
        existing_sfr_by_code = {item.sfr_id.strip().upper(): item for item in existing_sfrs}
        library_map = {item.sfr_component.strip().upper(): item for item in library_items}
        threat_by_code = {item.code.strip().upper(): item for item in threats}
        assumption_by_code = {item.code.strip().upper(): item for item in assumptions}
        osp_by_code = {item.code.strip().upper(): item for item in osps}

        added_objectives = 0
        added_sfrs = 0

        await update_task_progress(task_id, "objective_import.stage_2.persist")

        async with AsyncSessionLocal() as db:
            objective_ids = [item.id for item in existing_objectives]
            objective_sfr_rows = (await db.exec(
                select(ObjectiveSFR).where(ObjectiveSFR.objective_id.in_(objective_ids))
            )).all() if objective_ids else []
            threat_objective_rows = (await db.exec(
                select(ThreatObjective).where(ThreatObjective.objective_id.in_(objective_ids))
            )).all() if objective_ids else []
            assumption_objective_rows = (await db.exec(
                select(AssumptionObjective).where(AssumptionObjective.objective_id.in_(objective_ids))
            )).all() if objective_ids else []
            osp_objective_rows = (await db.exec(
                select(OSPObjective).where(OSPObjective.objective_id.in_(objective_ids))
            )).all() if objective_ids else []

            objective_by_code = dict(existing_objective_by_code)
            objective_sfr_pairs = {(row.objective_id, row.sfr_id) for row in objective_sfr_rows}
            threat_objective_pairs = {(row.threat_id, row.objective_id) for row in threat_objective_rows}
            assumption_objective_pairs = {(row.assumption_id, row.objective_id) for row in assumption_objective_rows}
            osp_objective_pairs = {(row.osp_id, row.objective_id) for row in osp_objective_rows}

            for item in objectives_data:
                code = str(item.get("code") or "").strip().upper()
                if not code:
                    continue
                if not (code.startswith("O.") or code.startswith("OE.")):
                    code = "O." + code
                obj_type = "OE" if code.startswith("OE.") else str(item.get("obj_type") or "O").strip().upper()
                if obj_type not in {"O", "OE"}:
                    obj_type = "OE" if code.startswith("OE.") else "O"

                objective = objective_by_code.get(code)
                if not objective:
                    objective = SecurityObjective(
                        toe_id=toe_id,
                        code=code,
                        obj_type=obj_type,
                        description=item.get("description"),
                        rationale="Imported from ST/PP documents",
                        review_status="draft",
                        ai_generated=True,
                    )
                    db.add(objective)
                    await db.flush()
                    objective_by_code[code] = objective
                    added_objectives += 1

                for source_code_raw in item.get("source_codes") or []:
                    source_code = str(source_code_raw).strip().upper()
                    if source_code.startswith("T."):
                        threat = threat_by_code.get(source_code)
                        if threat and (threat.id, objective.id) not in threat_objective_pairs:
                            db.add(ThreatObjective(threat_id=threat.id, objective_id=objective.id))
                            threat_objective_pairs.add((threat.id, objective.id))
                    elif source_code.startswith("A."):
                        assumption = assumption_by_code.get(source_code)
                        if assumption and (assumption.id, objective.id) not in assumption_objective_pairs:
                            db.add(AssumptionObjective(assumption_id=assumption.id, objective_id=objective.id))
                            assumption_objective_pairs.add((assumption.id, objective.id))
                    elif source_code.startswith("P."):
                        osp = osp_by_code.get(source_code)
                        if osp and (osp.id, objective.id) not in osp_objective_pairs:
                            db.add(OSPObjective(osp_id=osp.id, objective_id=objective.id))
                            osp_objective_pairs.add((osp.id, objective.id))

            await db.commit()

        await update_task_progress(task_id, "objective_import.stage_3.prepare")

        regex_sfr_codes: list[str] = []
        for block in sfr_context_blocks:
            for sfr_code in _extract_sfr_codes_from_text(block):
                if sfr_code not in regex_sfr_codes:
                    regex_sfr_codes.append(sfr_code)

        async with AsyncSessionLocal() as db:
            objective_rows = (await db.exec(
                select(SecurityObjective).where(
                    SecurityObjective.toe_id == toe_id,
                    SecurityObjective.deleted_at.is_(None),
                ).order_by(SecurityObjective.code)
            )).all()
            objective_by_code = {item.code.strip().upper(): item for item in objective_rows}

            sfr_rows = (await db.exec(
                select(SFR).where(SFR.toe_id == toe_id, SFR.deleted_at.is_(None))
            )).all()
            sfr_by_code = {item.sfr_id.strip().upper(): item for item in sfr_rows}

            existing_pairs_rows = (await db.exec(
                select(ObjectiveSFR).where(ObjectiveSFR.objective_id.in_([item.id for item in objective_rows]))
            )).all() if objective_rows else []
            objective_sfr_pairs = {(row.objective_id, row.sfr_id) for row in existing_pairs_rows}

            for sfr_code in regex_sfr_codes:
                if sfr_code in sfr_by_code:
                    continue
                library_item = library_map.get(sfr_code)
                sfr = SFR(
                    toe_id=toe_id,
                    sfr_library_id=library_item.id if library_item else None,
                    sfr_id=sfr_code,
                    source="st_pp",
                    customization_note=None,
                    ai_rationale="Extracted from ST/PP documents",
                    review_status="draft",
                )
                db.add(sfr)
                await db.flush()
                sfr_by_code[sfr_code] = sfr
                added_sfrs += 1

            await db.commit()

            objective_catalog = "\n".join(
                f"- {item.code} ({item.obj_type}): {item.description or '-'}"
                for item in objective_rows
            )

            batches = _chunked(regex_sfr_codes, 8)
            for batch_index, sfr_batch in enumerate(batches, start=1):
                await update_task_progress(task_id, f"objective_import.stage_3.batch_start|{batch_index}|{len(batches)}")
                batch_context = _build_sfr_batch_context(sfr_context_blocks, sfr_batch)
                mapping_prompt = f"""You are a CC(Common Criteria) expert. Map the following SFRs to the most relevant security objectives based on the ST/PP excerpts.

Security Objectives:
{objective_catalog or '-'}

Current SFR batch:
{chr(10).join(f'- {code}' for code in sfr_batch)}

Relevant document excerpts:
{batch_context}

Return JSON:
{{
  "mappings": [
    {{
      "sfr_id": "FDP_ACC.1",
      "objective_codes": ["O.EXAMPLE"],
      "mapping_rationale": "brief rationale"
    }}
  ]
}}

Rules:
- Only use objective codes from the provided Security Objectives list.
- Only use SFR IDs from the current batch.
- If no reliable mapping exists for an SFR, return it with an empty objective_codes array.
- Keep rationale concise."""

                try:
                    mapping_result = await ai.chat_json(mapping_prompt, max_tokens=4096)
                except Exception:
                    continue

                await update_task_progress(task_id, f"objective_import.stage_3.batch_ai|{batch_index}|{len(batches)}")

                for item in mapping_result.get("mappings", []) if isinstance(mapping_result, dict) else []:
                    sfr_code = str(item.get("sfr_id") or "").strip().upper()
                    sfr = sfr_by_code.get(sfr_code)
                    if not sfr:
                        continue
                    for objective_code_raw in item.get("objective_codes") or []:
                        objective_code = str(objective_code_raw).strip().upper()
                        objective = objective_by_code.get(objective_code)
                        if not objective:
                            continue
                        pair = (objective.id, sfr.id)
                        if pair in objective_sfr_pairs:
                            continue
                        db.add(ObjectiveSFR(
                            objective_id=objective.id,
                            sfr_id=sfr.id,
                            mapping_rationale=item.get("mapping_rationale") or "Imported from ST/PP documents",
                        ))
                        objective_sfr_pairs.add(pair)

                await db.commit()
                await update_task_progress(task_id, f"objective_import.stage_3.batch_save|{batch_index}|{len(batches)}")

        await finish_task(
            task_id,
            f"objective_import.done|{len(objectives_data)}|{len(regex_sfr_codes)}|{added_objectives}|{added_sfrs}"
        )

    except Exception as e:
        await fail_task(task_id, str(e))


async def objective_gen_task(ctx, toe_id: str, mode: str, task_id: str, language: str = "en"):
    """Security objective generation task (Phase 4)."""
    try:
        from app.models.toe import TOE
        from app.models.threat import Threat, Assumption, OSP
        from app.models.security import SecurityObjective, ThreatObjective, AssumptionObjective, OSPObjective
        from app.services.ai_service import get_ai_service

        language = (language or "en").lower()

        await update_task_progress(task_id, "Stage 1/4: Reading TOE information...")

        async with AsyncSessionLocal() as db:
            toe = (await db.exec(select(TOE).where(TOE.id == toe_id))).first()
            if not toe:
                await fail_task(task_id, "TOE not found")
                return

            threats = (await db.exec(
                select(Threat).where(Threat.toe_id == toe_id, Threat.deleted_at.is_(None))
            )).all()
            assumptions = (await db.exec(
                select(Assumption).where(Assumption.toe_id == toe_id, Assumption.deleted_at.is_(None))
            )).all()
            osps = (await db.exec(
                select(OSP).where(OSP.toe_id == toe_id, OSP.deleted_at.is_(None))
            )).all()
            existing_objectives = (await db.exec(
                select(SecurityObjective).where(
                    SecurityObjective.toe_id == toe_id,
                    SecurityObjective.deleted_at.is_(None),
                )
            )).all()
            ai = await get_ai_service(db, toe.user_id)

        if not ai:
            await fail_task(task_id, "No available AI model found. Please configure and verify an AI model first.")
            return

        await update_task_progress(task_id, "Stage 2/4: Preparing AI context...")

        threats_text = "\n".join(
            f"- {item.code}: {item.adverse_action or ''} (assets: {item.assets_affected or ''})"
            for item in threats[:30]
        )
        assumptions_text = "\n".join(f"- {item.code}: {item.description or ''}" for item in assumptions[:20])
        osps_text = "\n".join(f"- {item.code}: {item.description or ''}" for item in osps[:20])

        existing_summary = ""
        if mode == "incremental" and existing_objectives:
            codes = ", ".join(item.code for item in existing_objectives)
            existing_summary = f"\nExisting security objectives (do not duplicate): {codes}"

        await update_task_progress(task_id, "Stage 3/4: AI generating security objectives...")

        output_language = "Chinese" if language == "zh" else "English"
        prompt = f"""You are a Common Criteria security evaluation expert. Generate security objectives from the TOE context below.

TOE Name: {toe.name}
TOE Summary: {toe.brief_intro or 'None'}

Threats:
{threats_text or '(None)'}

Assumptions:
{assumptions_text or '(None)'}

Organizational Security Policies (OSPs):
{osps_text or '(None)'}
{existing_summary}

There are two objective types:
- O.XXX: security objectives that must be implemented by the TOE itself to counter threats or satisfy OSPs
- OE.XXX: environmental objectives that must be satisfied by the operational environment and typically correspond to assumptions

For each generated objective, identify the exact related threat / assumption / osp codes so the system can auto-create mappings.

Return JSON in this format:
{{
  "objectives": [
    {{
      "code": "O.AUTH_CONTROL",
      "obj_type": "O",
      "description": "The TOE shall enforce strong authentication so that only authorized users can access system functions.",
      "rationale": "Addresses threat T.UNAUTH_ACCESS by using access control and authentication to resist unauthorized access.",
      "linked_threat_codes": ["T.UNAUTH_ACCESS"],
      "linked_assumption_codes": [],
      "linked_osp_codes": []
    }}
  ]
}}

Requirements:
- Generate 6-15 security objectives
- O-type objectives should correspond to threats or OSPs
- OE-type objectives should correspond to assumptions
- Code format: O.VERB_NOUN or OE.VERB_NOUN in uppercase English
- description and rationale must be in {output_language}
- `linked_threat_codes`, `linked_assumption_codes`, and `linked_osp_codes` must only contain codes that actually exist in the provided input"""

        result = await ai.chat_json(prompt)
        objectives_data = result.get("objectives", []) if isinstance(result, dict) else []

        await update_task_progress(
            task_id,
            f"Stage 4/4: Writing {len(objectives_data)} security objectives...",
        )

        added = 0
        async with AsyncSessionLocal() as db:
            existing_codes = {item.code for item in existing_objectives}
            threat_by_code = {item.code.upper(): item for item in threats}
            assumption_by_code = {item.code.upper(): item for item in assumptions}
            osp_by_code = {item.code.upper(): item for item in osps}

            for objective_data in objectives_data:
                code = (objective_data.get("code") or "").strip().upper()
                if not code or code in existing_codes:
                    continue
                if not (code.startswith("O.") or code.startswith("OE.")):
                    code = "O." + code

                obj_type = objective_data.get("obj_type", "O")
                if code.startswith("OE."):
                    obj_type = "OE"

                objective = SecurityObjective(
                    toe_id=toe_id,
                    code=code,
                    obj_type=obj_type,
                    description=objective_data.get("description"),
                    rationale=objective_data.get("rationale"),
                    review_status="draft",
                    ai_generated=True,
                )
                db.add(objective)
                await db.flush()

                rationale_text = f"{objective_data.get('rationale') or ''} {objective_data.get('description') or ''}".upper()
                linked_threat_codes = {
                    str(item).strip().upper()
                    for item in (objective_data.get("linked_threat_codes") or [])
                    if str(item).strip()
                }
                linked_assumption_codes = {
                    str(item).strip().upper()
                    for item in (objective_data.get("linked_assumption_codes") or [])
                    if str(item).strip()
                }
                linked_osp_codes = {
                    str(item).strip().upper()
                    for item in (objective_data.get("linked_osp_codes") or [])
                    if str(item).strip()
                }

                for item_code in threat_by_code:
                    if item_code in rationale_text:
                        linked_threat_codes.add(item_code)
                for item_code in assumption_by_code:
                    if item_code in rationale_text:
                        linked_assumption_codes.add(item_code)
                for item_code in osp_by_code:
                    if item_code in rationale_text:
                        linked_osp_codes.add(item_code)

                for threat_code in linked_threat_codes:
                    threat = threat_by_code.get(threat_code)
                    if threat:
                        db.add(ThreatObjective(threat_id=threat.id, objective_id=objective.id))
                for assumption_code in linked_assumption_codes:
                    assumption = assumption_by_code.get(assumption_code)
                    if assumption:
                        db.add(AssumptionObjective(assumption_id=assumption.id, objective_id=objective.id))
                for osp_code in linked_osp_codes:
                    osp = osp_by_code.get(osp_code)
                    if osp:
                        db.add(OSPObjective(osp_id=osp.id, objective_id=objective.id))

                existing_codes.add(code)
                added += 1

            await db.commit()

        await finish_task(
            task_id,
            f"Objective generation complete, added {added} objectives",
        )

    except Exception as e:
        await fail_task(task_id, str(e))


async def sfr_library_import_task(ctx, task_id: str, file_path: str, mime_type: str, language: str = "en"):
    try:
        from app.models.ai_task import AITask
        from app.models.security import SFRLibrary
        from app.services.ai_service import get_ai_service

        await update_task_progress(task_id, "sfr_library_import.stage_1")

        async with AsyncSessionLocal() as db:
            task_row = (await db.exec(select(AITask).where(AITask.id == task_id))).first()
            if not task_row:
                return
            ai = await get_ai_service(db, task_row.user_id)
            if not ai:
                await fail_task(task_id, "No available AI model. Please configure and verify an AI model first")
                return

        document_text = await _extract_document_text(file_path, mime_type)
        if not document_text.strip():
            await fail_task(task_id, "The uploaded document could not be parsed into text")
            return

        await update_task_progress(task_id, "sfr_library_import.stage_2")

        candidate_sfr_ids = _extract_sfr_codes_from_text(document_text)
        if not candidate_sfr_ids:
            await fail_task(task_id, "No SFR IDs were detected in the uploaded document")
            return

        await update_task_progress(task_id, f"sfr_library_import.stage_2.chunk|{len(candidate_sfr_ids)}")

        def build_sfr_context(text: str, sfr_id: str, max_chars: int = 7000) -> str:
            source = text or ""
            upper_source = source.upper()
            target = sfr_id.upper()
            snippets: list[str] = []
            start = 0
            while True:
                index = upper_source.find(target, start)
                if index < 0:
                    break
                left = max(0, index - 1200)
                right = min(len(source), index + 2600)
                snippets.append(source[left:right])
                start = index + len(target)
                if len("\n\n---\n\n".join(snippets)) >= max_chars:
                    break
            if not snippets:
                return source[:max_chars]
            return "\n\n---\n\n".join(snippets)[:max_chars]

        aggregate: dict[str, dict] = {}
        total_candidates = len(candidate_sfr_ids)

        for index, sfr_id in enumerate(candidate_sfr_ids, start=1):
            await update_task_progress(task_id, f"sfr_library_import.stage_3.batch_start|{index}|{total_candidates}")
            context = build_sfr_context(document_text, sfr_id)
            prompt = f"""You are a CC (Common Criteria) security expert. Extract exactly one SFR from the provided document context.

TARGET SFR ID:
{sfr_id}

DOCUMENT CONTEXT:
{context}

INSTRUCTIONS:
- Extract only the target SFR ID shown above.
- Keep original wording for the name and detail. Do not summarize.
- Preserve the original document language exactly. Do not translate, rewrite, or paraphrase the extracted content.
- Dependencies should be returned as a single comma-separated string when present.
- Determine sfr_class and sfr_family from the component when possible.
- If class or family names are explicit in the context, return them. Otherwise return null.
- If the target SFR cannot be confirmed from the context, return null for the missing fields but keep the target SFR ID.

Return JSON:
{{
  "sfr": {{
    "sfr_id": "{sfr_id}",
    "sfr_name": "Subset access control",
    "sfr_detail": "exact requirement text",
    "dependencies": "FIA_UID.1, FIA_UAU.1",
    "sfr_class": "FDP",
    "sfr_class_name": "User Data Protection",
    "sfr_family": "FDP_ACC",
    "sfr_family_name": "Subset access control"
  }}
}}"""
            extract_system = "You are a professional CC security expert. Return strict JSON only."
            await update_task_progress(task_id, f"sfr_library_import.stage_3.batch_ai|{index}|{total_candidates}")
            result = await ai.chat_json(prompt, system=extract_system, max_tokens=2048)
            raw = result.get("sfr") if isinstance(result, dict) else None
            if not isinstance(raw, dict):
                raw = {"sfr_id": sfr_id}
            sfr_component = str(raw.get("sfr_id") or sfr_id).strip().upper()
            existing = aggregate.get(sfr_component, {})
            aggregate[sfr_component] = {
                "sfr_id": sfr_component,
                "sfr_name": raw.get("sfr_name") or existing.get("sfr_name"),
                "sfr_detail": raw.get("sfr_detail") or existing.get("sfr_detail"),
                "dependencies": raw.get("dependencies") or existing.get("dependencies"),
                "sfr_class": raw.get("sfr_class") or existing.get("sfr_class"),
                "sfr_class_name": raw.get("sfr_class_name") or existing.get("sfr_class_name"),
                "sfr_family": raw.get("sfr_family") or existing.get("sfr_family"),
                "sfr_family_name": raw.get("sfr_family_name") or existing.get("sfr_family_name"),
            }

        await update_task_progress(task_id, "sfr_library_import.stage_4")

        async with AsyncSessionLocal() as db:
            rows = (await db.exec(select(SFRLibrary))).all()
            class_name_map: dict[str, str] = {}
            family_name_map: dict[str, str] = {}
            for item in rows:
                if item.sfr_class and item.sfr_class_name and item.sfr_class not in class_name_map:
                    class_name_map[item.sfr_class] = item.sfr_class_name
                if item.sfr_family and item.sfr_family_name and item.sfr_family not in family_name_map:
                    family_name_map[item.sfr_family] = item.sfr_family_name

            imported = 0
            updated = 0
            total_items = len(aggregate)

            for index, (sfr_component, raw) in enumerate(aggregate.items(), start=1):
                await update_task_progress(task_id, f"sfr_library_import.stage_4.save|{index}|{max(total_items, 1)}")
                family = sfr_component.split('.', 1)[0] if '.' in sfr_component else sfr_component
                sfr_class = family.split('_', 1)[0] if '_' in family else family
                next_class = str(raw.get("sfr_class") or sfr_class).strip().upper() or sfr_class
                next_family = str(raw.get("sfr_family") or family).strip().upper() or family
                next_class_name = str(raw.get("sfr_class_name") or "").strip() or class_name_map.get(next_class) or next_class
                next_family_name = str(raw.get("sfr_family_name") or "").strip() or family_name_map.get(next_family) or next_family
                next_name = str(raw.get("sfr_name") or "").strip() or sfr_component
                next_detail = str(raw.get("sfr_detail") or "").strip() or None
                next_dependencies = str(raw.get("dependencies") or "").strip() or None

                existing = (await db.exec(select(SFRLibrary).where(SFRLibrary.sfr_component == sfr_component))).first()
                if existing:
                    existing.sfr_class = next_class
                    existing.sfr_class_name = next_class_name
                    existing.sfr_family = next_family
                    existing.sfr_family_name = next_family_name
                    existing.sfr_component_name = next_name
                    existing.description = next_detail
                    existing.dependencies = next_dependencies
                    db.add(existing)
                    updated += 1
                else:
                    db.add(SFRLibrary(
                        sfr_class=next_class,
                        sfr_class_name=next_class_name,
                        sfr_family=next_family,
                        sfr_family_name=next_family_name,
                        sfr_component=sfr_component,
                        sfr_component_name=next_name,
                        description=next_detail,
                        dependencies=next_dependencies,
                    ))
                    imported += 1

            await db.commit()

        await finish_task(task_id, f"sfr_library_import.done|{len(aggregate)}|{imported}|{updated}")
    except Exception as e:
        await fail_task(task_id, str(e))
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


async def sfr_match_task(ctx, toe_id: str, mode: str, task_id: str, language: str = "en"):
    """SFR pre-matching task (Phase 4)."""
    try:
        from app.models.toe import TOE
        from app.models.security import SecurityObjective, SFR, SFRLibrary, ObjectiveSFR
        from app.services.ai_service import get_ai_service

        language = (language or "en").lower()
        output_language = "Chinese" if language == "zh" else "English"

        await update_task_progress(task_id, "Phase 1/5: Reading security objectives...")

        async with AsyncSessionLocal() as db:
            toe_res = await db.exec(select(TOE).where(TOE.id == toe_id))
            toe = toe_res.first()
            if not toe:
                await fail_task(task_id, "TOE not found")
                return

            obj_res = await db.exec(
                select(SecurityObjective).where(
                    SecurityObjective.toe_id == toe_id,
                    SecurityObjective.deleted_at.is_(None),
                ).order_by(SecurityObjective.code)
            )
            objectives = obj_res.all()

            existing_sfr_res = await db.exec(
                select(SFR).where(SFR.toe_id == toe_id, SFR.deleted_at.is_(None))
            )
            existing_sfrs = existing_sfr_res.all()
            objective_sfr_rows = (await db.exec(
                select(ObjectiveSFR).where(ObjectiveSFR.sfr_id.in_([item.id for item in existing_sfrs]))
            )).all() if existing_sfrs else []

        if not objectives:
            await finish_task(task_id, "No security objectives found. Skipping SFR matching")
            return

        await update_task_progress(task_id, "Phase 2/5: Reading SFR library...")

        async with AsyncSessionLocal() as db:
            lib_res = await db.exec(
                select(SFRLibrary).order_by(SFRLibrary.sfr_component)
            )
            lib_items = lib_res.all()

        library_map = {item.sfr_component: item for item in lib_items}
        objective_by_code = {item.code.strip().upper(): item for item in objectives}
        lib_text = "\n".join(
            f"- {item.sfr_component}: {item.sfr_component_name} [{item.sfr_family}]"
            for item in lib_items
        )
        toe_context_parts = [
            f"Name: {toe.name}",
            f"Type: {toe.toe_type}",
            f"Summary: {toe.brief_intro or toe.description or '-'}",
            f"Type description: {toe.toe_type_desc or '-'}",
            f"Usage scenarios: {toe.toe_usage or toe.usage_and_security_features or '-'}",
            f"Major security features: {toe.major_security_features or toe.security_features_overview or '-'}",
            f"Logical scope: {toe.logical_scope or toe.boundary or '-'}",
            f"Hardware interfaces: {toe.hw_interfaces or '-'}",
            f"Software interfaces: {toe.sw_interfaces or '-'}",
            f"External interfaces: {toe.external_interfaces or '-'}",
        ]
        toe_context = "\n".join(toe_context_parts)
        mapped_objective_ids = {row.objective_id for row in objective_sfr_rows}
        sfr_target_objectives = [item for item in objectives if item.obj_type == "O"]
        target_objectives = sfr_target_objectives if mode == "full" else [item for item in sfr_target_objectives if item.id not in mapped_objective_ids]
        if not target_objectives:
            await finish_task(task_id, "All O-type objectives already have SFR mappings. Skipping incremental matching")
            return

        await update_task_progress(task_id, "Phase 3/5: Matching SFRs for each objective...")

        async with AsyncSessionLocal() as db:
            ai = await get_ai_service(db, toe.user_id)
        if not ai:
            await fail_task(task_id, "No available AI model found. Please configure and verify an AI model first.")
            return

        added = 0
        mappings_added = 0

        async def load_current_state(db):
            current_sfrs = (await db.exec(
                select(SFR).where(SFR.toe_id == toe_id, SFR.deleted_at.is_(None))
            )).all()
            current_sfr_by_code = {item.sfr_id.upper(): item for item in current_sfrs}
            current_sfr_ids = [item.id for item in current_sfrs]
            mapping_rows = (await db.exec(
                select(ObjectiveSFR).where(ObjectiveSFR.sfr_id.in_(current_sfr_ids))
            )).all() if current_sfr_ids else []
            mapping_pairs = {(row.objective_id, row.sfr_id) for row in mapping_rows}
            mapped_objective_ids = {row.objective_id for row in mapping_rows}
            mapped_sfr_ids = {row.sfr_id for row in mapping_rows}
            return current_sfrs, current_sfr_by_code, mapping_pairs, mapped_objective_ids, mapped_sfr_ids

        async def apply_sfr_matches(db, rows):
            nonlocal added, mappings_added

            current_sfrs, current_sfr_by_code, mapping_pairs, _, _ = await load_current_state(db)
            del current_sfrs

            async def ensure_sfr_with_dependencies(
                sfr_component: str,
                source: str,
                rationale: Optional[str],
                objective_codes: list[str],
                parent_component: Optional[str] = None,
                visited: Optional[set[str]] = None,
            ):
                nonlocal added, mappings_added

                normalized_component = (sfr_component or "").strip().upper()
                if not normalized_component:
                    return None
                if visited is None:
                    visited = set()
                if normalized_component in visited:
                    return current_sfr_by_code.get(normalized_component)
                visited.add(normalized_component)

                lib = library_map.get(normalized_component)
                if not lib:
                    return None

                sfr = current_sfr_by_code.get(normalized_component)
                normalized_source = _normalize_sfr_source(source)
                effective_rationale = rationale
                if parent_component:
                    effective_rationale = effective_rationale or f"Auto-added as a dependency of {parent_component}"

                if not sfr:
                    sfr = SFR(
                        toe_id=toe_id,
                        sfr_library_id=lib.id,
                        sfr_id=normalized_component,
                        source=normalized_source,
                        ai_rationale=effective_rationale,
                        dependency_warning=None,
                        review_status="draft",
                    )
                    db.add(sfr)
                    await db.flush()
                    current_sfr_by_code[normalized_component] = sfr
                    added += 1
                else:
                    sfr.source = _normalize_sfr_source(sfr.source)
                    if effective_rationale and (not sfr.ai_rationale or mode == "full"):
                        sfr.ai_rationale = effective_rationale
                    db.add(sfr)

                for objective_code in objective_codes:
                    objective = objective_by_code.get(objective_code)
                    if not objective:
                        continue
                    pair = (objective.id, sfr.id)
                    if pair in mapping_pairs:
                        continue
                    mapping_rationale = effective_rationale
                    if parent_component:
                        mapping_rationale = mapping_rationale or f"Added as a dependency of {parent_component}"
                    db.add(ObjectiveSFR(
                        objective_id=objective.id,
                        sfr_id=sfr.id,
                        mapping_rationale=mapping_rationale,
                    ))
                    mapping_pairs.add(pair)
                    mappings_added += 1

                for dependency_component in _parse_sfr_dependencies(lib.dependencies):
                    await ensure_sfr_with_dependencies(
                        dependency_component,
                        normalized_source,
                        f"Auto-added as a dependency of {normalized_component}",
                        objective_codes,
                        parent_component=normalized_component,
                        visited=visited,
                    )

                return sfr

            for row in rows:
                sfr_component = (row.get("sfr_id") or "").strip().upper()
                if not sfr_component:
                    continue

                objective_codes = [
                    str(code).strip().upper()
                    for code in (row.get("objective_codes") or [])
                    if str(code).strip()
                ]
                objective_codes = list(dict.fromkeys(objective_codes))
                if not objective_codes:
                    continue
                await ensure_sfr_with_dependencies(
                    sfr_component,
                    row.get("source", "ai"),
                    row.get("ai_rationale"),
                    objective_codes,
                )

        async def run_objective_match(objective: SecurityObjective, force_at_least_one: bool = False) -> list[dict]:
            current_links = [
                row.sfr_id for row in objective_sfr_rows
                if row.objective_id == objective.id and row.sfr_id in {item.id for item in existing_sfrs}
            ]
            current_sfr_labels = [
                item.sfr_id for item in existing_sfrs if item.id in current_links
            ]
            current_sfr_note = (
                f"Current TOE SFR mappings for this objective: {', '.join(sorted(current_sfr_labels))}"
                if current_sfr_labels else "This objective does not yet have TOE SFR mappings"
            )
            strict_note = "You must return at least 1 SFR." if force_at_least_one else "Return an empty list if you cannot make a reliable decision."
            prompt = f"""You are a CC (Common Criteria) security evaluation expert. For the single security objective below, choose the most appropriate SFRs from the full SFR catalog.

TOE context:
{toe_context}

Current security objective:
- {objective.code} ({objective.obj_type}): {objective.description or '-'}

{current_sfr_note}

Full SFR catalog:
{lib_text}

Return JSON:
{{
    "objective_code": "{objective.code}",
    "sfrs": [
        {{
            "sfr_id": "FDP_ACC.1",
            "ai_rationale": "Explain why this SFR supports the security objective"
        }}
    ]
}}

Rules:
- Only handle objective {objective.code}
- One objective may map to multiple SFRs
- Prefer the 1-3 strongest matches
- Return existing TOE SFRs as well; the system will reuse them automatically
- sfr_id must come from the full SFR catalog
- ai_rationale must be in {output_language}
- {strict_note}"""
            match_result = await ai.chat_json(prompt)
            rows = []
            for sfr_item in (match_result.get("sfrs") or []):
                rows.append({
                    "sfr_id": sfr_item.get("sfr_id"),
                    "source": "ai",
                    "ai_rationale": sfr_item.get("ai_rationale"),
                    "objective_codes": [objective.code],
                })

            deduped: dict[str, dict] = {}
            for row in rows:
                sfr_component = str(row.get("sfr_id") or "").strip().upper()
                if not sfr_component or sfr_component not in library_map:
                    continue
                if sfr_component not in deduped:
                    deduped[sfr_component] = {
                        "sfr_id": sfr_component,
                        "source": "ai",
                        "ai_rationale": row.get("ai_rationale"),
                        "objective_codes": [objective.code],
                    }
            return list(deduped.values())

        total_targets = len(target_objectives)
        for index, objective in enumerate(target_objectives, start=1):
            await update_task_progress(task_id, f"Phase 4/5: Matching objective {index}/{total_targets} - {objective.code}")
            rows = await run_objective_match(objective)
            if not rows:
                rows = await run_objective_match(objective, force_at_least_one=True)
            if not rows:
                continue
            async with AsyncSessionLocal() as db:
                await apply_sfr_matches(db, rows)
                await db.commit()

        async with AsyncSessionLocal() as db:
            current_sfrs, _, _, mapped_objective_ids, mapped_sfr_ids = await load_current_state(db)
        uncovered_objectives = [item for item in sfr_target_objectives if item.id not in mapped_objective_ids]
        orphan_sfrs = [item for item in current_sfrs if item.id not in mapped_sfr_ids]

        uncovered_objective_count = len(uncovered_objectives)
        orphan_sfr_count = len([item for item in current_sfrs if item.id not in mapped_sfr_ids])
        summary = f"SFR matching completed, processed {total_targets} objectives, added {added} SFRs, added {mappings_added} mappings"
        if uncovered_objective_count or orphan_sfr_count:
            summary += f", {uncovered_objective_count} uncovered objectives, {orphan_sfr_count} orphan SFRs"

        await finish_task(task_id, summary)

    except Exception as e:
        await fail_task(task_id, str(e))


async def sfr_stpp_validate_task(ctx, toe_id: str, task_id: str, language: str = "en"):
    """Validate SFRs mapped to objectives using the TOE's ST/PP documents and automatically fill missing dependencies."""
    try:
        from app.models.toe import TOE, TOEFile
        from app.models.security import SecurityObjective, SFR, SFRLibrary, ObjectiveSFR
        from app.services.ai_service import get_ai_service

        language = (language or "en").lower()
        output_language = "Chinese" if language == "zh" else "English"

        await update_task_progress(task_id, "Phase 1/5: Reading ST/PP documents...")

        async with AsyncSessionLocal() as db:
            toe_res = await db.exec(select(TOE).where(TOE.id == toe_id))
            toe = toe_res.first()
            if not toe:
                await fail_task(task_id, "TOE not found")
                return

            file_res = await db.exec(
                select(TOEFile).where(
                    TOEFile.toe_id == toe_id,
                    TOEFile.file_category == "st_pp",
                    TOEFile.process_status == "ready",
                    TOEFile.deleted_at.is_(None),
                )
            )
            st_pp_files = file_res.all()
            if not st_pp_files:
                await fail_task(task_id, "No ST/PP documents are available")
                return

            obj_res = await db.exec(
                select(SecurityObjective).where(
                    SecurityObjective.toe_id == toe_id,
                    SecurityObjective.obj_type == "O",
                    SecurityObjective.deleted_at.is_(None),
                ).order_by(SecurityObjective.code)
            )
            objectives = obj_res.all()
            if not objectives:
                await finish_task(task_id, "No O-type objectives found. Skipping ST/PP validation")
                return

            existing_sfr_res = await db.exec(
                select(SFR).where(SFR.toe_id == toe_id, SFR.deleted_at.is_(None))
            )
            existing_sfrs = existing_sfr_res.all()
            objective_sfr_rows = (await db.exec(
                select(ObjectiveSFR).where(ObjectiveSFR.sfr_id.in_([item.id for item in existing_sfrs]))
            )).all() if existing_sfrs else []

            lib_res = await db.exec(select(SFRLibrary).order_by(SFRLibrary.sfr_component))
            lib_items = lib_res.all()

        await update_task_progress(task_id, "Phase 2/5: Organizing documents and SFR library...")

        document_parts: list[str] = []
        document_names: list[str] = []
        for file in st_pp_files:
            if not file.extracted_text_path or not os.path.exists(file.extracted_text_path):
                continue
            with open(file.extracted_text_path, "r", encoding="utf-8", errors="ignore") as fp:
                content = fp.read()
            if not content.strip():
                continue
            document_names.append(file.original_filename)
            document_parts.append(f"[{file.original_filename}]\n{content[:50000]}")

        if not document_parts:
            await fail_task(task_id, "ST/PP documents do not contain usable text yet. Confirm parsing completed successfully.")
            return

        library_map = {item.sfr_component: item for item in lib_items}
        objective_by_code = {item.code.strip().upper(): item for item in objectives}
        document_text = "\n\n".join(document_parts)
        candidate_sfrs = [code for code in _extract_sfr_codes_from_text(document_text) if code in library_map]
        if not candidate_sfrs:
            await finish_task(task_id, "No usable SFR components were detected in the ST/PP documents. No additions were made.")
            return

        toe_context = "\n".join([
            f"Name: {toe.name}",
            f"Type: {toe.toe_type}",
            f"Summary: {toe.brief_intro or toe.description or '-'}",
            f"Major security features: {toe.major_security_features or toe.security_features_overview or '-'}",
            f"Logical scope: {toe.logical_scope or toe.boundary or '-'}",
        ])
        candidate_sfr_text = "\n".join(f"- {code}" for code in candidate_sfrs)

        async with AsyncSessionLocal() as db:
            ai = await get_ai_service(db, toe.user_id)
        if not ai:
            await fail_task(task_id, "No available AI model found. Please configure and verify an AI model first.")
            return

        added = 0
        mappings_added = 0
        matched_objectives = 0

        async def load_current_state(db):
            current_sfrs = (await db.exec(
                select(SFR).where(SFR.toe_id == toe_id, SFR.deleted_at.is_(None))
            )).all()
            current_sfr_by_code = {item.sfr_id.upper(): item for item in current_sfrs}
            current_sfr_ids = [item.id for item in current_sfrs]
            mapping_rows = (await db.exec(
                select(ObjectiveSFR).where(ObjectiveSFR.sfr_id.in_(current_sfr_ids))
            )).all() if current_sfr_ids else []
            mapping_pairs = {(row.objective_id, row.sfr_id) for row in mapping_rows}
            mapped_objective_ids = {row.objective_id for row in mapping_rows}
            mapped_sfr_ids = {row.sfr_id for row in mapping_rows}
            return current_sfrs, current_sfr_by_code, mapping_pairs, mapped_objective_ids, mapped_sfr_ids

        async def apply_sfr_matches(db, rows):
            nonlocal added, mappings_added

            current_sfrs, current_sfr_by_code, mapping_pairs, _, _ = await load_current_state(db)
            del current_sfrs

            async def ensure_sfr_with_dependencies(
                sfr_component: str,
                source: str,
                rationale: Optional[str],
                objective_codes: list[str],
                parent_component: Optional[str] = None,
                visited: Optional[set[str]] = None,
            ):
                nonlocal added, mappings_added

                normalized_component = (sfr_component or "").strip().upper()
                if not normalized_component:
                    return None
                if visited is None:
                    visited = set()
                if normalized_component in visited:
                    return current_sfr_by_code.get(normalized_component)
                visited.add(normalized_component)

                lib = library_map.get(normalized_component)
                if not lib:
                    return None

                sfr = current_sfr_by_code.get(normalized_component)
                normalized_source = _normalize_sfr_source(source)
                effective_rationale = rationale
                if parent_component:
                    effective_rationale = effective_rationale or f"Auto-added as a dependency of {parent_component}"

                if not sfr:
                    sfr = SFR(
                        toe_id=toe_id,
                        sfr_library_id=lib.id,
                        sfr_id=normalized_component,
                        source=normalized_source,
                        ai_rationale=effective_rationale,
                        dependency_warning=None,
                        review_status="draft",
                    )
                    db.add(sfr)
                    await db.flush()
                    current_sfr_by_code[normalized_component] = sfr
                    added += 1
                else:
                    sfr.source = _normalize_sfr_source(sfr.source)
                    if effective_rationale and not sfr.ai_rationale:
                        sfr.ai_rationale = effective_rationale
                    db.add(sfr)

                for objective_code in objective_codes:
                    objective = objective_by_code.get(objective_code)
                    if not objective:
                        continue
                    pair = (objective.id, sfr.id)
                    if pair in mapping_pairs:
                        continue
                    mapping_rationale = effective_rationale
                    if parent_component:
                        mapping_rationale = mapping_rationale or f"Added as a dependency of {parent_component}"
                    db.add(ObjectiveSFR(
                        objective_id=objective.id,
                        sfr_id=sfr.id,
                        mapping_rationale=mapping_rationale,
                    ))
                    mapping_pairs.add(pair)
                    mappings_added += 1

                for dependency_component in _parse_sfr_dependencies(lib.dependencies):
                    await ensure_sfr_with_dependencies(
                        dependency_component,
                        normalized_source,
                        f"Auto-added as a dependency of {normalized_component}",
                        objective_codes,
                        parent_component=normalized_component,
                        visited=visited,
                    )

                return sfr

            for row in rows:
                sfr_component = (row.get("sfr_id") or "").strip().upper()
                objective_codes = [
                    str(code).strip().upper()
                    for code in (row.get("objective_codes") or [])
                    if str(code).strip()
                ]
                if not sfr_component or not objective_codes:
                    continue
                await ensure_sfr_with_dependencies(
                    sfr_component,
                    row.get("source", "st_pp"),
                    row.get("ai_rationale"),
                    objective_codes,
                )

        total_targets = len(objectives)
        for index, objective in enumerate(objectives, start=1):
            await update_task_progress(task_id, f"Phase 4/5: Matching objective {index}/{total_targets} - {objective.code}")

            objective_context = _build_st_pp_objective_context(
                document_text,
                objective.code,
                objective.description,
            )
            prompt = f"""You are a CC (Common Criteria) security evaluation expert. Based on the ST/PP document content, determine whether the current security objective is explicitly present or directly supported; if it is, identify the SFR components that support it.

TOE context:
{toe_context}

Current security objective:
- {objective.code}: {objective.description or '-'}

Candidate SFR components (choose only from this list):
{candidate_sfr_text}

ST/PP document excerpt:
{objective_context}

Return JSON:
{{
    "matched": true,
    "matched_objective_code": "{objective.code}",
    "rationale": "Explain why the objective exists in the ST/PP and why these SFRs correspond to it",
    "sfrs": ["FDP_ACC.1", "FMT_MTD.1"]
}}

Rules:
- Set matched=true only when the document explicitly shows or directly supports the objective
- sfrs must be selected only from the candidate SFR component list
- Return at most 6 directly relevant SFRs
- If you cannot confirm the match, return matched=false and an empty array
- rationale must be in {output_language}"""

            match_result = await ai.chat_json(prompt)
            matched = bool(match_result.get("matched"))
            sfr_rows = []
            for sfr_component in (match_result.get("sfrs") or []):
                normalized_component = str(sfr_component or "").strip().upper()
                if normalized_component and normalized_component in library_map:
                    sfr_rows.append({
                        "sfr_id": normalized_component,
                        "source": "st_pp",
                        "ai_rationale": f"ST/PP validation supplement: {match_result.get('rationale') or 'Document support was found'}",
                        "objective_codes": [objective.code],
                    })

            deduped_rows: dict[str, dict] = {}
            for row in sfr_rows:
                deduped_rows[row["sfr_id"]] = row

            if matched and deduped_rows:
                matched_objectives += 1
                async with AsyncSessionLocal() as db:
                    await apply_sfr_matches(db, list(deduped_rows.values()))
                    await db.commit()

        await update_task_progress(task_id, "Phase 5/5: Summarizing validation results...")

        async with AsyncSessionLocal() as db:
            current_sfrs, _, _, mapped_objective_ids, mapped_sfr_ids = await load_current_state(db)

        uncovered_objectives = [item for item in objectives if item.id not in mapped_objective_ids]
        orphan_sfrs = [item for item in current_sfrs if item.id not in mapped_sfr_ids]
        source_ref = ", ".join(document_names)
        summary = f"ST/PP validation completed, matched {matched_objectives}/{total_targets} objectives, added {added} SFRs, added {mappings_added} mappings"
        if source_ref:
            summary += f", reference documents: {source_ref}"
        if uncovered_objectives or orphan_sfrs:
            summary += f", {len(uncovered_objectives)} uncovered objectives, {len(orphan_sfrs)} orphan SFRs"

        await finish_task(task_id, summary)

    except Exception as e:
        await fail_task(task_id, str(e))


async def test_gen_task(ctx, toe_id: str, sfr_ids: list, task_id: str):
    """Test case generation task (Phase 5)."""
    try:
        from app.models.toe import TOE
        from app.models.security import SFR
        from app.models.test_case import TestCase
        from app.services.ai_service import get_ai_service

        await update_task_progress(task_id, "Phase 1/3: Reading SFR information...")

        async with AsyncSessionLocal() as db:
            toe_res = await db.exec(select(TOE).where(TOE.id == toe_id))
            toe = toe_res.first()
            if not toe:
                await fail_task(task_id, "TOE not found")
                return

            sfr_stmt = select(SFR).where(SFR.toe_id == toe_id, SFR.deleted_at.is_(None))
            if sfr_ids:
                sfr_stmt = sfr_stmt.where(SFR.id.in_(sfr_ids))
            sfr_res = await db.exec(sfr_stmt)
            sfrs = sfr_res.all()

            # Existing test titles (avoid duplicates)
            existing_res = await db.exec(
                select(TestCase.title).where(TestCase.toe_id == toe_id, TestCase.deleted_at.is_(None))
            )
            existing_titles = {r for r in existing_res.all()}

        if not sfrs:
            await finish_task(task_id, "No SFRs found. Skipping test case generation")
            return

        await update_task_progress(task_id, "Phase 2/3: AI generating test cases...")

        sfr_text = "\n".join(
            f"- SFR ID: {s.sfr_id}, rationale: {s.ai_rationale or 'Standard component'}" for s in sfrs[:20]
        )

        async with AsyncSessionLocal() as db:
            ai = await get_ai_service(db, toe.user_id)
        if not ai:
            await fail_task(task_id, "No available AI model found. Please configure and verify an AI model first.")
            return
        prompt = f"""You are a CC (Common Criteria) security testing expert. Generate test cases from the TOE and SFR list below.

TOE Name: {toe.name}
TOE Description: {(toe.description or '')[:400]}

SFR List:
{sfr_text}

Generate 1-3 test cases for each SFR and return JSON:
{{
    "test_cases": [
        {{
            "sfr_id": "FDP_ACC.1",
            "test_type": "independent",
            "title": "Access control policy verification",
            "objective": "Verify that the TOE enforces the access control policy required by FDP_ACC.1",
            "precondition": "A test user account has been created and the TOE is running normally",
            "test_steps": "1. Attempt to access a protected resource with an unauthorized account\\n2. Verify access is denied\\n3. Access the resource with an authorized account\\n4. Verify access is granted",
            "expected_result": "Unauthorized access is denied and authorized access succeeds"
        }}
    ]
}}

test_type must be one of: independent / interface / scenario
SFR IDs must come from the list above.
All descriptions must be in English."""

        result = await ai.chat_json(prompt)
        test_cases_data = result.get("test_cases", [])

        await update_task_progress(task_id, f"Phase 3/3: Writing {len(test_cases_data)} test cases...")

        # Build sfr_id -> SFR.id map
        sfr_map = {s.sfr_id: s.id for s in sfrs}

        added = 0
        async with AsyncSessionLocal() as db:
            for td in test_cases_data:
                sfr_id_str = (td.get("sfr_id") or "").strip().upper()
                sfr_db_id = sfr_map.get(sfr_id_str)
                if not sfr_db_id:
                    continue
                title = (td.get("title") or "").strip()
                if not title or title in existing_titles:
                    continue
                tc = TestCase(
                    toe_id=toe_id,
                    primary_sfr_id=sfr_db_id,
                    test_type=td.get("test_type", "independent"),
                    title=title,
                    objective=td.get("objective"),
                    precondition=td.get("precondition"),
                    test_steps=td.get("test_steps"),
                    expected_result=td.get("expected_result"),
                    review_status="draft",
                    ai_generated=True,
                )
                db.add(tc)
                existing_titles.add(title)
                added += 1
            await db.commit()

        await finish_task(task_id, f"Test case generation completed, added {added} cases")

    except Exception as e:
        await fail_task(task_id, str(e))


async def st_export_task(ctx, toe_id: str, config: dict, task_id: str):
    """ST document export task (Phase 5) - generate a structured HTML ST document."""
    try:
        from app.models.toe import TOE, TOEAsset
        from app.models.threat import Threat, Assumption, OSP
        from app.models.security import SecurityObjective, SFR
        from app.models.test_case import TestCase
        from app.core.config import settings

        await update_task_progress(task_id, "Reading TOE data...")

        async with AsyncSessionLocal() as db:
            toe_res = await db.exec(select(TOE).where(TOE.id == toe_id))
            toe = toe_res.first()
            if not toe:
                await fail_task(task_id, "TOE not found")
                return

            assets_res = await db.exec(select(TOEAsset).where(TOEAsset.toe_id == toe_id, TOEAsset.deleted_at.is_(None)))
            assets = assets_res.all()

            threats, assumptions, osps, objectives, sfrs, tests = [], [], [], [], [], []

            if config.get("include_threats", True):
                r = await db.exec(select(Threat).where(Threat.toe_id == toe_id, Threat.deleted_at.is_(None)))
                threats = r.all()
            if config.get("include_assumptions", True):
                r = await db.exec(select(Assumption).where(Assumption.toe_id == toe_id, Assumption.deleted_at.is_(None)))
                assumptions = r.all()
            if config.get("include_osps", True):
                r = await db.exec(select(OSP).where(OSP.toe_id == toe_id, OSP.deleted_at.is_(None)))
                osps = r.all()
            if config.get("include_objectives", True):
                r = await db.exec(select(SecurityObjective).where(SecurityObjective.toe_id == toe_id, SecurityObjective.deleted_at.is_(None)))
                objectives = r.all()
            if config.get("include_sfrs", True):
                r = await db.exec(select(SFR).where(SFR.toe_id == toe_id, SFR.deleted_at.is_(None)))
                sfrs = r.all()
            if config.get("include_test_cases", False):
                r = await db.exec(select(TestCase).where(TestCase.toe_id == toe_id, TestCase.deleted_at.is_(None)))
                tests = r.all()

        await update_task_progress(task_id, "Generating ST document content...")

        author = config.get("author") or "System generated"
        version = config.get("version_string") or toe.version or "1.0"
        now = datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d")

        def _section(title: str, rows: list, cols: list, row_fn) -> str:
            if not rows:
                return f"<h2>{title}</h2><p><em>(No records)</em></p>"
            header = "".join(f"<th>{c}</th>" for c in cols)
            body = "".join(
                "<tr>" + "".join(f"<td>{v}</td>" for v in row_fn(r)) + "</tr>"
                for r in rows
            )
            return f"<h2>{title}</h2><table border='1' cellpadding='6' cellspacing='0' style='border-collapse:collapse;width:100%'><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>"

        html = f"""<!DOCTYPE html>
    <html lang="en"><head><meta charset="UTF-8">
    <title>Security Target (ST) - {toe.name}</title>
<style>
body{{font-family:SimSun,serif;margin:40px;line-height:1.6;color:#222}}
h1{{text-align:center;font-size:24px;margin-bottom:4px}}
.meta{{text-align:center;color:#666;margin-bottom:32px}}
h2{{font-size:16px;border-bottom:2px solid #333;padding-bottom:4px;margin-top:32px}}
table{{font-size:13px}}
td,th{{padding:6px 10px;vertical-align:top}}
th{{background:#f0f0f0}}
p{{font-size:14px}}
</style>
</head><body>
<h1>Security Target (ST)</h1>
<div class="meta">Product: {toe.name} | Version: {version} | Author: {author} | Date: {now}</div>

<h2>1. ST Introduction</h2>
<p><strong>TOE Name:</strong> {toe.name}<br>
<strong>Version:</strong> {version}<br>
<strong>Type:</strong> {toe.toe_type}<br>
<strong>Summary:</strong> {toe.brief_intro or '—'}</p>

<h2>2. TOE Description</h2>
<p>{(toe.description or '—').replace(chr(10), '<br>')}</p>

<h2>3. TOE Boundary</h2>
<p>{(toe.boundary or '—').replace(chr(10), '<br>')}</p>

<h2>4. Operational Environment</h2>
<p>{(toe.operational_env or '—').replace(chr(10), '<br>')}</p>

{_section(
    "5. Protected Assets",
    assets,
    ["Name", "Type", "Importance", "Reason"],
    lambda a: [a.name, a.asset_type, a.importance, a.importance_reason or "—"]
)}

{_section(
    "6. Threats",
    threats,
    ["Code", "Threat Agent", "Adverse Action", "Affected Assets", "Likelihood", "Impact", "Risk Level"],
    lambda t: [t.code, t.threat_agent or "—", t.adverse_action or "—",
               t.assets_affected or "—", t.likelihood, t.impact, t.risk_level]
) if config.get("include_threats") else ""}

{_section(
    "7. Assumptions",
    assumptions,
    ["Code", "Description"],
    lambda a: [a.code, a.description or "—"]
) if config.get("include_assumptions") else ""}

{_section(
    "8. Organizational Security Policies (OSP)",
    osps,
    ["Code", "Description"],
    lambda o: [o.code, o.description or "—"]
) if config.get("include_osps") else ""}

{_section(
    "9. Security Objectives",
    objectives,
    ["Code", "Type", "Description", "Rationale"],
    lambda o: [o.code, o.obj_type, o.description or "—", o.rationale or "—"]
) if config.get("include_objectives") else ""}

{_section(
    "10. Security Functional Requirements (SFR)",
    sfrs,
    ["SFR ID", "Source", "Customization Note"],
    lambda s: [s.sfr_id, s.source, s.customization_note or "—"]
) if config.get("include_sfrs") else ""}

{_section(
    "11. Test Cases",
    tests,
    ["Title", "Type", "Test Steps", "Expected Result"],
    lambda t: [t.title, t.test_type, (t.test_steps or "—").replace(chr(10), "<br>"),
               t.expected_result or "—"]
) if config.get("include_test_cases") else ""}

</body></html>"""

        # Save file
        export_dir = os.path.join(settings.storage_path, "exports", toe_id)
        os.makedirs(export_dir, exist_ok=True)
        filename = f"ST_{toe.name.replace(' ', '_')}_{now}.html"
        file_path = os.path.join(export_dir, filename)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)

        await finish_task(task_id, f"ST document generated: {filename}", download_url=file_path)

    except Exception as e:
        await fail_task(task_id, str(e))


async def risk_summary_task(ctx, toe_id: str, task_id: str, language: str = "en"):
    """Risk assessment summary generation task (Phase 5)."""
    try:
        from app.models.toe import TOE
        from app.models.threat import Threat
        from app.models.risk import RiskAssessment, TOERiskCache
        from app.services.ai_service import get_ai_service

        await update_task_progress(task_id, "Reading risk data...")

        async with AsyncSessionLocal() as db:
            toe_res = await db.exec(select(TOE).where(TOE.id == toe_id))
            toe = toe_res.first()
            if not toe:
                await fail_task(task_id, "TOE not found")
                return

            t_res = await db.exec(
                select(Threat).where(Threat.toe_id == toe_id, Threat.deleted_at.is_(None))
            )
            threats = t_res.all()

            ra_res = await db.exec(
                select(RiskAssessment).where(RiskAssessment.toe_id == toe_id)
            )
            assessments = {ra.threat_id: ra for ra in ra_res.all()}

        await update_task_progress(task_id, "Generating AI risk summary...")

        threats_summary = "\n".join(
            f"- {t.code}: risk={t.risk_level}, status={t.review_status}, "
            f"treatment={assessments[t.id].residual_risk if t.id in assessments else 'not assessed'}"
            for t in threats[:30]
        )

        async with AsyncSessionLocal() as db:
            ai = await get_ai_service(db, toe.user_id)
        if not ai:
            await fail_task(task_id, "No available AI model found. Please configure and verify an AI model first.")
            return
        language = (language or "en").lower()
        output_language = "Chinese" if language == "zh" else "English"
        prompt = f"""Based on the TOE risk list below, generate a concise {output_language} risk summary in under 200 words.

TOE: {toe.name}
Threat list:
{threats_summary or '(no threat records)'}

Return plain summary text only. Do not add formatting or a title."""

        summary_text = await ai.chat(prompt)

        # Update cache
        async with AsyncSessionLocal() as db:
            cache_res = await db.exec(
                select(TOERiskCache).where(TOERiskCache.toe_id == toe_id)
            )
            cache = cache_res.first()
            if cache:
                cache.ai_summary = summary_text
                cache.ai_generated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                cache.is_stale = False
            else:
                cache = TOERiskCache(
                    toe_id=toe_id,
                    risk_score=0,
                    risk_level="low",
                    ai_summary=summary_text,
                    ai_generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    is_stale=False,
                )
            db.add(cache)
            await db.commit()

        await finish_task(task_id, "Risk summary generated")

    except Exception as e:
        await fail_task(task_id, str(e))


async def blind_spot_suggestions_task(ctx, toe_id: str, task_id: str, user_id: str, language: str = "en"):
    """Generate AI blind-spot suggestions for a TOE."""
    try:
        import json as _json
        from app.models.toe import TOE, TOEAsset
        from app.models.threat import Threat, Assumption, OSP
        from app.models.security import SecurityObjective, SFR, ObjectiveSFR
        from app.models.test_case import TestCase
        from app.models.risk import BlindSpotSuggestion
        from app.services.ai_service import get_ai_service

        await update_task_progress(task_id, "Reading TOE data...")

        async with AsyncSessionLocal() as db:
            toe_res = await db.exec(select(TOE).where(TOE.id == toe_id))
            toe = toe_res.first()
            if not toe:
                await fail_task(task_id, "TOE not found")
                return

            assets = (await db.exec(
                select(TOEAsset).where(TOEAsset.toe_id == toe_id, TOEAsset.deleted_at.is_(None))
            )).all()
            threats = (await db.exec(
                select(Threat).where(Threat.toe_id == toe_id, Threat.deleted_at.is_(None))
            )).all()
            assumptions = (await db.exec(
                select(Assumption).where(Assumption.toe_id == toe_id)
            )).all()
            osps = (await db.exec(
                select(OSP).where(OSP.toe_id == toe_id)
            )).all()
            objectives = (await db.exec(
                select(SecurityObjective).where(
                    SecurityObjective.toe_id == toe_id,
                    SecurityObjective.deleted_at.is_(None),
                )
            )).all()
            sfrs = (await db.exec(
                select(SFR).where(SFR.toe_id == toe_id, SFR.deleted_at.is_(None))
            )).all()
            tests = (await db.exec(
                select(TestCase).where(TestCase.toe_id == toe_id, TestCase.deleted_at.is_(None))
            )).all()

        await update_task_progress(task_id, "Generating AI suggestions...")

        # Build summary for AI
        asset_summary = ", ".join(f"{a.name}(type={a.asset_type}, importance={a.importance})" for a in assets[:20]) or "none"
        threat_summary = ", ".join(f"{t.code}(risk={t.risk_level})" for t in threats[:20]) or "none"
        assumption_summary = ", ".join(a.code for a in assumptions[:10]) or "none"
        osp_summary = ", ".join(o.code for o in osps[:10]) or "none"
        obj_summary = ", ".join(f"{o.code}(type={o.obj_type})" for o in objectives[:20]) or "none"
        sfr_summary = ", ".join(f"{s.sfr_id}(status={s.review_status})" for s in sfrs[:30]) or "none"
        test_summary = f"{len(tests)} test cases, {sum(1 for t in tests if t.review_status == 'confirmed')} confirmed"

        async with AsyncSessionLocal() as db:
            ai = await get_ai_service(db, user_id)
        if not ai:
            await fail_task(task_id, "No available AI model found. Please configure and verify an AI model first.")
            return

        language = (language or "en").lower()
        output_language = "Chinese" if language == "zh" else "English"
        prompt = f"""You are a professional CC (Common Criteria) security evaluation expert. Based on the TOE security data below, analyze possible blind spots and provide 3-6 specific, actionable suggestions.

TOE: {toe.name}

Current data:
- Assets: {asset_summary}
- Threats: {threat_summary}
- Assumptions: {assumption_summary}
- OSPs: {osp_summary}
- Security Objectives: {obj_summary}
- SFRs: {sfr_summary}
- Tests: {test_summary}

Analyze from these angles:
1. asset: missing important asset types or attack surfaces
2. threat: unconsidered attack vectors or new attack techniques
3. sfr: insufficient SFR selection or missing security functions
4. test: inadequate test coverage or missing critical scenarios
5. general: emerging vulnerabilities, supply chain risk, and similar concerns

Return a JSON array only. Each item must contain:
- category: "asset" | "threat" | "sfr" | "test" | "general"
- content: one concise suggestion in {output_language}, within 100 characters if possible

Return only the JSON array and no additional text."""

        result_text = await ai.chat(prompt, max_tokens=2048)

        # Parse JSON from response
        suggestions = []
        try:
            # Try to extract JSON array from response
            text = result_text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0]
            suggestions = _json.loads(text.strip())
            if not isinstance(suggestions, list):
                suggestions = []
        except (_json.JSONDecodeError, ValueError):
            # Fallback: treat as single general suggestion
            if result_text.strip():
                suggestions = [{"category": "general", "content": result_text.strip()[:200]}]

        valid_categories = {"asset", "threat", "sfr", "test", "general"}

        async with AsyncSessionLocal() as db:
            # Delete old non-ignored suggestions for this TOE
            old_res = await db.exec(
                select(BlindSpotSuggestion).where(
                    BlindSpotSuggestion.toe_id == toe_id,
                    BlindSpotSuggestion.deleted_at.is_(None),
                    BlindSpotSuggestion.is_ignored == False,
                )
            )
            for old in old_res.all():
                old.soft_delete()
                db.add(old)

            # Insert new suggestions
            count = 0
            for s in suggestions[:8]:
                cat = s.get("category", "general")
                content = s.get("content", "")
                if not content or cat not in valid_categories:
                    continue
                suggestion = BlindSpotSuggestion(
                    toe_id=toe_id,
                    category=cat,
                    content=content[:500],
                )
                db.add(suggestion)
                count += 1

            await db.commit()

        await finish_task(task_id, f"Generated {count} security suggestions")

    except Exception as e:
        await fail_task(task_id, str(e))
