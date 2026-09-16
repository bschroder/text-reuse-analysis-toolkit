import json
import os
import pandas as pd
from collections import defaultdict
import string
import difflib

def extract_text_from_xml(xml_path):
    """Extract plain text from XML, supporting TEI namespace."""
    from lxml import etree
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(xml_path, parser)
        ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
        body = tree.xpath('//tei:body', namespaces=ns)
        if body:
            text = "".join(body[0].itertext())
        else:
            text = "".join(tree.getroot().itertext())
        return text
    except Exception as e:
        print(f"Error parsing XML {xml_path}: {e}")
        return ""

def clean_latin_text(text):
    """Handle logical negation symbol and normalize whitespace."""
    import re
    text = re.sub(r'¬\s*\n\s*', '', text)
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

def is_minor_change(w1, w2):
    clean1 = w1.lower().strip(string.punctuation)
    clean2 = w2.lower().strip(string.punctuation)
    if clean1 == clean2:
        return True
    # Handle common Latin orthographic variations
    clean1_lat = clean1.replace('v', 'u').replace('j', 'i').replace('y', 'i')
    clean2_lat = clean2.replace('v', 'u').replace('j', 'i').replace('y', 'i')
    return clean1_lat == clean2_lat

def generate_diff_html(target_text, reference_text):
    t_words = target_text.split()
    r_words = reference_text.split()
    matcher = difflib.SequenceMatcher(None, t_words, r_words)
    opcodes = matcher.get_opcodes()

    left_html = ""
    right_html = ""
    
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'equal':
            left_html += f'<span class="match" title="Exact Match">{" ".join(t_words[i1:i2])}</span> '
            right_html += f'<span class="match" title="Exact Match">{" ".join(r_words[j1:j2])}</span> '
        
        elif tag == 'replace':
            t_sub = t_words[i1:i2]
            r_sub = r_words[j1:j2]
            
            if len(t_sub) == len(r_sub):
                for tw, rw in zip(t_sub, r_sub):
                    if is_minor_change(tw, rw):
                        left_html += f'<span class="minor-change" title="Minor Change (Variation of \'{rw}\')">{tw}</span> '
                        right_html += f'<span class="minor-change" title="Minor Change (Variation of \'{tw}\')">{rw}</span> '
                    else:
                        left_html += f'<span class="major-change" title="Word Replaced (differs from \'{rw}\')">{tw}</span> '
                        right_html += f'<span class="major-change" title="Word Replaced (differs from \'{tw}\')">{rw}</span> '
            else:
                left_html += f'<span class="major-change" title="Word Replaced">{" ".join(t_sub)}</span> '
                right_html += f'<span class="major-change" title="Word Replaced">{" ".join(r_sub)}</span> '
        
        elif tag == 'delete':
            left_html += f'<span class="deletion" title="Word Removed (Missing in reference text)">{" ".join(t_words[i1:i2])}</span> '
        
        elif tag == 'insert':
            right_html += f'<span class="addition" title="Word Added (Inserted by reference author)">{" ".join(r_words[j1:j2])}</span> '

    return left_html, right_html

def get_context_strings(text, start, end, padding=150):
    if not text or start is None or end is None:
        return "", ""
    before = text[max(0, start-padding):start]
    after = text[end:min(len(text), end+padding)]
    
    before_parts = before.split(" ")
    if len(before_parts) > 1:
        before = " ".join(before_parts[1:]) + " "
        
    after_parts = after.split(" ")
    if len(after_parts) > 1:
        after = " " + " ".join(after_parts[:-1])
        
    return before, after

def generate_pretty_html(json_path, target_dir, output_dir):
    if not os.path.exists(json_path):
        print(f"File {json_path} not found.")
        return

    with open(json_path, 'r', encoding='utf-8') as f:
        try:
            matches = json.load(f)
        except json.JSONDecodeError:
            print(f"Error decoding JSON from {json_path}")
            return

    os.makedirs(output_dir, exist_ok=True)

    # Group matches by target_id
    matches_by_target = defaultdict(list)
    for m in matches:
        matches_by_target[m.get('target_id', 'unknown')].append(m)

    unique_refs = set(m['reference_id'] for m in matches)
    total_refs = len(unique_refs)

    css = """
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f4f7f6; }
        h1, h2 { color: #2c3e50; border-bottom: 2px solid #2c3e50; padding-bottom: 10px; }
        h2 { margin-top: 50px; border-bottom: 1px solid #7f8c8d; }
        
        .viz-section { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); border: 1px solid #ddd; margin-bottom: 30px; position: sticky; top: 10px; z-index: 1000; }
        
        .barcode-wrapper { position: relative; margin-bottom: 10px; user-select: none; }
        .barcode-container { background: #eee; height: 50px; width: 100%; position: relative; border-radius: 4px; overflow: hidden; border: 1px solid #bbb; cursor: crosshair; }
        .barcode-tick { position: absolute; height: 100%; background: #e74c3c; opacity: 0.4; pointer-events: none; border-left: 1px solid rgba(0,0,0,0.1); }
        .selection-overlay { position: absolute; height: 100%; background: rgba(52, 152, 219, 0.4); border: 2px solid #2980b9; top: 0; pointer-events: none; display: none; z-index: 5; }
        
        .zoom-info { font-size: 0.85em; color: #666; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }
        
        .match-group { background: white; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 30px; overflow: hidden; border: 1px solid #ddd; }
        .target-text { background: #2c3e50; color: white; padding: 15px 20px; font-size: 1.1em; border-left: 5px solid #e74c3c; }
        .target-meta { font-size: 0.75em; color: #bdc3c7; font-weight: normal; margin-top: 5px; display: block; }
        .reference-list { padding: 0; margin: 0; list-style: none; }
        .reference-item { padding: 15px 20px; border-bottom: 1px solid #eee; }
        .reference-item:last-child { border-bottom: none; }
        .ref-meta { font-size: 0.9em; color: #7f8c8d; margin-bottom: 5px; }
        .ref-id { font-family: monospace; background: #ebf5fb; padding: 2px 5px; border-radius: 3px; color: #2980b9; font-size: 0.85em; }
        .ref-source { text-transform: uppercase; font-weight: bold; color: #e67e22; }
        .exact-match { background: #fff9c4; padding: 10px; border-radius: 4px; margin-top: 10px; font-family: "Georgia", serif; border-left: 3px solid #f1c40f; font-size: 0.95em; }
        .stats { margin-bottom: 20px; font-style: italic; color: #666; }
        .anchor { display: block; position: relative; top: -180px; visibility: hidden; }
        
        .filter-controls { display: flex; gap: 20px; flex-wrap: wrap; margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; }
        .filter-group { flex: 1; min-width: 200px; }
        .filter-group label { margin-right: 10px; font-size: 0.9em; cursor: pointer; }
        .hidden { display: none !important; }
        
        .home-link { display: block; margin-bottom: 20px; font-weight: bold; color: #2c3e50; text-decoration: none; }
        button { cursor: pointer; padding: 5px 10px; border-radius: 4px; border: 1px solid #ccc; background: #f8f8f8; font-size: 0.85em; }
        button:hover { background: #eee; }

        /* Diff Highlighting */
        .match { background-color: transparent; }
        .minor-change { background-color: #e8f8f5; border-bottom: 2px dotted #3498db; cursor: help; }
        .deletion { background-color: #fbdada; color: #c0392b; text-decoration: line-through; cursor: help; }
        .addition { background-color: #d4fcbc; color: #27ae60; font-weight: bold; cursor: help; }
        .major-change { background-color: #fef9e7; border-bottom: 2px solid #f39c12; cursor: help; }
        
        /* Side by Side Layout */
        .side-by-side { display: flex; gap: 20px; margin-top: 15px; }
        .column { flex: 1; padding: 15px; border: 1px solid #e1e4e8; border-radius: 8px; background: #fafafa; font-family: Georgia, serif; line-height: 1.6; font-size: 1.05em; position: relative; }
        .column-title { font-size: 0.75em; color: #7f8c8d; text-transform: uppercase; margin-bottom: 10px; letter-spacing: 1px; font-weight: bold; font-family: sans-serif; }
        .diff-legend { margin-top: 10px; padding: 10px; background: #fdfdfd; border: 1px solid #ddd; border-radius: 6px; font-size: 0.85em; }
        .diff-legend span { margin-right: 15px; padding: 2px 6px; border-radius: 3px; }
        
        /* Context Display */
        .context-text { color: #95a5a6; font-style: italic; font-size: 0.95em; transition: all 0.3s ease; display: none; }
        .context-text.show { display: inline; }
        .toggle-btn { background: #3498db; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 0.85em; margin-bottom: 10px; transition: background 0.2s; display: inline-block; margin-top: 10px; margin-left: 20px; }
        .toggle-btn:hover { background: #2980b9; }
        .match-core { padding: 3px; border-radius: 4px; transition: all 0.3s ease; }
        .context-active .match-core { background: rgba(241, 196, 15, 0.15); border-left: 3px solid #f1c40f; padding-left: 8px; }
    """

    file_cache = {}

    def get_cached_text(path, is_xml):
        if path not in file_cache:
            if not os.path.exists(path):
                return ""
            if is_xml:
                file_cache[path] = clean_latin_text(extract_text_from_xml(path))
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    file_cache[path] = clean_latin_text(f.read())
        return file_cache[path]

    # 1. GENERATE INDIVIDUAL REPORTS
    for target_id, target_matches in matches_by_target.items():
        available_sources = sorted(list(set(
            str(m['reference_id'].split(os.sep)[0] if os.sep in m['reference_id'] else (m['reference_id'].split('/')[0] if '/' in m['reference_id'] else 'root')) for m in target_matches
        )))
        
        target_txt_path = os.path.join(target_dir, f"{target_id}.txt")
        target_xml_path = os.path.join(target_dir, f"{target_id}.xml")
        
        target_total_len = 1
        t_text = ""
        for ext in ['.txt', '.xml']:
            t_path = os.path.join(target_dir, target_id + ext)
            if os.path.exists(t_path):
                t_text = get_cached_text(t_path, is_xml=(ext == '.xml'))
                break
        
        if t_text:
            target_total_len = len(t_text)
        
        grouped_segments = defaultdict(list)
        for m in target_matches:
            indices = m.get('target_indices')
            if indices and len(indices) >= 2:
                key = (m['target_match'], indices[0], indices[1])
                grouped_segments[key].append(m)
        
        sorted_segments = sorted(grouped_segments.items(), key=lambda x: x[0][1])

        # Barcode Map with data-match-id
        barcode_html = f'<div class="barcode-container" id="barcode-main" title="Visual map for {target_id}">'
        for j, (key, _) in enumerate(sorted_segments):
            _, start, end = key
            left = (start / target_total_len) * 100
            width = ((end - start) / target_total_len) * 100
            # Ensure visible width
            draw_width = max(0.1, width)
            barcode_html += f'<div class="barcode-tick" data-match-id="{j}" style="left: {left}%; width: {draw_width}%;"></div>'
        barcode_html += '<div class="selection-overlay" id="selection-overlay"></div></div>'

        filter_html = f"""
            <div class="filter-controls">
                <div class="filter-group">
                    <strong>Source Corpora:</strong><br>
                    {" ".join([f'<label><input type="checkbox" class="source-filter" value="{s}" checked> {s.upper()}</label>' for s in available_sources])}
                    <div style="margin-top: 10px;">
                        <button onclick="toggleAllFilters(true)">Select All</button>
                        <button onclick="toggleAllFilters(false)">Deselect All</button>
                    </div>
                </div>
            </div>
        """

        safe_target_filename = target_id.replace(os.sep, '_').replace(' ', '_')

        individual_html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>Reuse Report: {target_id}</title>
            <style>{css}</style>
        </head>
        <body>
            <a href="flexible_reuse_report.html" class="home-link">← Back to Master Report</a>
            <h1>Text Reuse Report: {target_id}</h1>
            
            <div class="diff-legend">
                <strong>Legend (Hover over highlights for details):</strong>
                <span class="match">Exact Match</span>
                <span class="minor-change">Minor Change (Punctuation/Spelling)</span>
                <span class="major-change">Word Replaced</span>
                <span class="addition">Word Added</span>
                <span class="deletion">Word Removed</span>
            </div>

            <div class="viz-section">
                <div class="zoom-info">
                    <span><strong>Text Reuse Map</strong> (Click and drag to filter range)</span>
                    <div id="filter-status">Showing all matches</div>
                    <button onclick="resetFilters()">Reset All Filters</button>
                </div>
                
                <div class="barcode-wrapper" id="barcode-wrapper">
                    {barcode_html}
                </div>
                {filter_html}
            </div>

            <div class="stats">
                Total unique reference works: {len(set(m['reference_id'] for m in target_matches))}<br>
                Total reuse segments found: <span id="visible-count">{len(grouped_segments)}</span> / {len(grouped_segments)}
            </div>

            <div id="matches-container">
        """

        for j, (key, ref_matches) in enumerate(sorted_segments):
            target_text_match, start, end = key
            t_before_ctx, t_after_ctx = get_context_strings(t_text, start, end)
            
            individual_html += f"""
            <div class="match-group" id="match-group-{j}" data-group-id="{j}" data-start="{start}" data-end="{end}">
                <a class="anchor" id="match-{j}"></a>
                <div class="target-text">
                    "{target_text_match}"
                    <span class="target-meta">Location: characters {start} - {end}</span>
                </div>
                <button class="toggle-btn" onclick="toggleContext({j})">Show Context (±20 words)</button>
                <ul class="reference-list">
            """
            
            match_index = 0
            for rm in ref_matches:
                ref_id = rm.get('reference_id', 'unknown')
                source = str(ref_id.split(os.sep)[0] if os.sep in ref_id else (ref_id.split('/')[0] if '/' in ref_id else 'root'))
                
                r_text = ""
                for ext in ['.txt', '.xml']:
                    r_path = os.path.join('reference_texts', ref_id + ext)
                    if os.path.exists(r_path):
                        r_text = get_cached_text(r_path, is_xml=(ext == '.xml'))
                        break
                        
                r_start, r_end = rm.get('reference_indices', [None, None])
                r_before_ctx, r_after_ctx = get_context_strings(r_text, r_start, r_end)
                left_diff_html, right_diff_html = generate_diff_html(target_text_match, rm['reference_match'])
                
                uid = f"{j}-{match_index}"
                match_index += 1
                
                side_by_side_html = f"""
                <div class="side-by-side" id="sbs-{uid}">
                    <div class="column">
                        <div class="column-title">Target Text</div>
                        <span class="context-text" id="t-before-{uid}">[...]{t_before_ctx}</span>
                        <span class="match-core" id="t-core-{uid}">{left_diff_html}</span>
                        <span class="context-text" id="t-after-{uid}">{t_after_ctx}[...]</span>
                    </div>
                    <div class="column">
                        <div class="column-title">Reference Text</div>
                        <span class="context-text" id="r-before-{uid}">[...]{r_before_ctx}</span>
                        <span class="match-core" id="r-core-{uid}">{right_diff_html}</span>
                        <span class="context-text" id="r-after-{uid}">{r_after_ctx}[...]</span>
                    </div>
                </div>
                """
                
                individual_html += f"""
                    <li class="reference-item" data-source="{source}" data-uid="{uid}">
                        <div class="ref-meta">
                            <span class="ref-id">{ref_id}</span>
                            <span class="ref-source">[{source}]</span>
                        </div>
                        {side_by_side_html}
                    </li>
                """
            individual_html += "</ul></div>"
        
        individual_html += f"""
            </div>
        <script>
            const targetTotalLen = {target_total_len};
            const barcodeMain = document.getElementById('barcode-main');
            const selectionOverlay = document.getElementById('selection-overlay');
            const filterStatus = document.getElementById('filter-status');
            const visibleCountSpan = document.getElementById('visible-count');
            
            let isSelecting = false;
            let startX = 0;
            let selectionRange = null; 

            // Context Toggle
            function toggleContext(groupId) {{
                const group = document.getElementById(`match-group-${{groupId}}`);
                const items = group.querySelectorAll('.reference-item');
                let isShowing = false;
                if (items.length > 0) {{
                    const firstUid = items[0].dataset.uid;
                    const firstEl = document.getElementById(`t-before-${{firstUid}}`);
                    isShowing = firstEl && firstEl.classList.contains('show');
                }}
                items.forEach(item => {{
                    const uid = item.dataset.uid;
                    [`t-before-${{uid}}`, `t-after-${{uid}}`, `r-before-${{uid}}`, `r-after-${{uid}}`].forEach(id => {{
                        const el = document.getElementById(id);
                        if (el) el.classList.toggle('show', !isShowing);
                    }});
                    [`t-core-${{uid}}`, `r-core-${{uid}}`].forEach(id => {{
                        const el = document.getElementById(id);
                        if (el && el.parentNode) el.parentNode.classList.toggle('context-active', !isShowing);
                    }});
                }});
                const btn = group.querySelector(`.toggle-btn`);
                if (btn) btn.innerText = isShowing ? 'Show Context (±20 words)' : 'Hide Context';
            }}

            // Barcode Selection Logic
            barcodeMain.addEventListener('mousedown', (e) => {{
                isSelecting = true;
                const rect = barcodeMain.getBoundingClientRect();
                startX = e.clientX - rect.left;
                selectionOverlay.style.display = 'block';
                selectionOverlay.style.left = startX + 'px';
                selectionOverlay.style.width = '0px';
                e.preventDefault();
            }});

            window.addEventListener('mousemove', (e) => {{
                if (!isSelecting) return;
                const rect = barcodeMain.getBoundingClientRect();
                let currentX = e.clientX - rect.left;
                currentX = Math.max(0, Math.min(currentX, rect.width));
                const left = Math.min(startX, currentX);
                const width = Math.abs(currentX - startX);
                selectionOverlay.style.left = left + 'px';
                selectionOverlay.style.width = width + 'px';
                const s = Math.floor((left / rect.width) * targetTotalLen);
                const f = Math.ceil(((left + width) / rect.width) * targetTotalLen);
                selectionRange = {{ start: s, end: f }};
                filterStatus.innerHTML = `<strong>Range Filter Active:</strong> Characters ${{s.toLocaleString()}} - ${{f.toLocaleString()}}`;
            }});

            window.addEventListener('mouseup', () => {{
                if (isSelecting) {{
                    isSelecting = false;
                    updateVisibility();
                }}
            }});

            function resetFilters() {{
                selectionRange = null;
                selectionOverlay.style.display = 'none';
                filterStatus.innerText = 'Showing all matches';
                document.querySelectorAll('.source-filter').forEach(f => f.checked = true);
                updateVisibility();
            }}

            function toggleAllFilters(state) {{
                document.querySelectorAll('.source-filter').forEach(f => f.checked = state);
                updateVisibility();
            }}

            function updateVisibility() {{
                const activeSources = Array.from(document.querySelectorAll('.source-filter'))
                    .filter(f => f.checked).map(f => f.value);
                let visibleCount = 0;
                document.querySelectorAll('.match-group').forEach(group => {{
                    const groupStart = parseInt(group.dataset.start);
                    const groupEnd = parseInt(group.dataset.end);
                    let inRange = !selectionRange || (groupStart <= selectionRange.end && groupEnd >= selectionRange.start);
                    let hasVisibleSource = false;
                    group.querySelectorAll('.reference-item').forEach(item => {{
                        const isVisible = activeSources.includes(item.dataset.source);
                        item.classList.toggle('hidden', !isVisible);
                        if (isVisible) hasVisibleSource = true;
                    }});
                    const groupVisible = inRange && hasVisibleSource;
                    group.classList.toggle('hidden', !groupVisible);
                    if (groupVisible) visibleCount++;
                    const tick = document.querySelector(`.barcode-tick[data-match-id="${{group.dataset.groupId}}"]`);
                    if (tick) tick.classList.toggle('hidden', !groupVisible);
                }});
                if(visibleCountSpan) visibleCountSpan.innerText = visibleCount;
            }}
            document.querySelectorAll('.source-filter').forEach(f => f.addEventListener('change', updateVisibility));
        </script>
        </body></html>
        """
        with open(os.path.join(output_dir, f"report_{safe_target_filename}.html"), 'w', encoding='utf-8') as f:
            f.write(individual_html)

    # 2. GENERATE MASTER REPORT
    nav_links = "".join([f'<li><a href="report_{t.replace(os.sep, "_").replace(" ", "_")}.html">{t}</a></li>' for t in sorted(matches_by_target.keys())])
    master_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"><title>Text Reuse Analysis Report</title><style>{css}</style></head>
    <body>
        <h1>Multi-Target Text Reuse Analysis</h1>
        <div class="stats">Total unique reference works: {total_refs}<br>Total targets analyzed: {len(matches_by_target)}</div>
        <h2>Summary by Target</h2>
    """
    for target_id in sorted(matches_by_target.keys()):
        safe_target_filename = target_id.replace(os.sep, '_').replace(' ', '_')
        target_matches = matches_by_target[target_id]
        master_html += f"""
        <div class="target-summary">
            <h3><a href="report_{safe_target_filename}.html">{os.path.basename(target_id)}</a></h3>
            <p style="color: #7f8c8d; font-size: 0.85em; margin-top: -10px;">ID: {target_id}</p>
            <p>Found matches in <strong>{len(set(m["reference_id"] for m in target_matches))}</strong> unique reference works. ({len(target_matches)} total matches)</p>
        </div>
        """
    master_html += "</body></html>"
    with open(os.path.join(output_dir, 'flexible_reuse_report.html'), 'w', encoding='utf-8') as f:
        f.write(master_html)
    print(f"Reports generated in {output_dir}")

if __name__ == "__main__":
    generate_pretty_html('results/flexible_matches.json', 'target_texts', 'results')
