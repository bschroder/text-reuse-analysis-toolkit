from text_matcher.matcher import Matcher, Text
import json
import os
import re
import pandas as pd
from tqdm import tqdm
from datetime import datetime
from lxml import etree

def clean_latin_text(text):
    """Handle logical negation symbol and normalize whitespace."""
    # Handle word breaks: "word¬\nnext" -> "wordnext"
    text = re.sub(r'¬\s*\n\s*', '', text)
    # Replace single newlines with space
    text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)
    # Remove multiple spaces
    text = re.sub(r' +', ' ', text)
    return text.strip()

def extract_text_from_xml(xml_path):
    """Extract plain text from XML, supporting TEI namespace."""
    try:
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(xml_path, parser)
        # Handle TEI namespace if present
        ns = {'tei': 'http://www.tei-c.org/ns/1.0'}
        body = tree.xpath('//tei:body', namespaces=ns)
        if body:
            text = "".join(body[0].itertext())
        else:
            # Fallback to all text in the document
            text = "".join(tree.getroot().itertext())
        return text
    except Exception as e:
        print(f"Error parsing XML {xml_path}: {e}")
        return ""

def load_run_log(log_path):
    if os.path.exists(log_path):
        return pd.read_csv(log_path)
    else:
        return pd.DataFrame(columns=['target_id', 'reference_id', 'timestamp', 'match_count', 'threshold', 'cutoff', 'ngramSize', 'status'])

def update_run_log(log_path, log_df, entry):
    # entry is a dict
    new_df = pd.concat([log_df, pd.DataFrame([entry])], ignore_index=True)
    new_df.to_csv(log_path, index=False)
    return new_df

def get_all_files(directory):
    """Recursively get all .txt and .xml files in a directory."""
    all_files = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".txt") or file.endswith(".xml"):
                all_files.append(os.path.join(root, file))
    return all_files

def get_text_from_file(file_path):
    """Load text from .txt or .xml file and apply cleaning."""
    if file_path.endswith('.xml'):
        text = extract_text_from_xml(file_path)
    else:
        with open(file_path, 'r', encoding='utf-8') as f:
            text = f.read()
    
    return clean_latin_text(text)

def run_flexible_analysis(target_dir, reference_dir, results_path, log_path, threshold=2, cutoff=4, ngramSize=3):
    target_files = get_all_files(target_dir)
    reference_files = get_all_files(reference_dir)
    
    log_df = load_run_log(log_path)
    
    if os.path.exists(results_path):
        with open(results_path, 'r', encoding='utf-8') as f:
            try:
                results = json.load(f)
            except:
                results = []
    else:
        results = []

    print(f"Flexible Analysis: {len(target_files)} target(s) vs {len(reference_files)} reference(s)")

    for t_file in target_files:
        # Use relative path as ID to avoid collisions in subfolders
        target_id = os.path.relpath(t_file, target_dir).replace('.txt', '').replace('.xml', '')
        target_text = get_text_from_file(t_file)
        
        if not target_text:
            continue
            
        print(f"\nProcessing Target: {target_id}")
        target_obj = Text(target_text, target_id, removeStopwords=False)

        for r_file in tqdm(reference_files, desc=f"Scanning for {target_id}"):
            reference_id = os.path.relpath(r_file, reference_dir).replace('.txt', '').replace('.xml', '')
            
            already_done = log_df[
                (log_df['target_id'] == target_id) &
                (log_df['reference_id'] == reference_id) &
                (log_df['threshold'] == threshold) &
                (log_df['cutoff'] == cutoff) &
                (log_df['ngramSize'] == ngramSize)
            ]
            
            if not already_done.empty:
                continue

            ref_text = get_text_from_file(r_file)
            
            if not ref_text:
                continue

            try:
                ref_obj = Text(ref_text, reference_id, removeStopwords=False)
                matcher = Matcher(target_obj, ref_obj, threshold=threshold, cutoff=cutoff, ngramSize=ngramSize)
                
                matches_count = 0
                if matcher.numMatches > 0:
                    for match in matcher.extended_matches:
                        matches_count += 1
                        lengthA = match.sizeA + matcher.ngramSize - 1
                        lengthB = match.sizeB + matcher.ngramSize - 1
                        
                        results.append({
                            'target_id': target_id,
                            'reference_id': reference_id,
                            'target_match': matcher.getTokensText(target_obj, match.a, lengthA),
                            'reference_match': matcher.getTokensText(ref_obj, match.b, lengthB),
                            'target_indices': matcher.getLocations(target_obj, match.a, lengthA),
                            'reference_indices': matcher.getLocations(ref_obj, match.b, lengthB),
                            'size_a': match.sizeA,
                            'size_b': match.sizeB
                        })
                
                # Log success
                log_df = update_run_log(log_path, log_df, {
                    'target_id': target_id,
                    'reference_id': reference_id,
                    'timestamp': datetime.now().isoformat(),
                    'match_count': matches_count,
                    'threshold': threshold,
                    'cutoff': cutoff,
                    'ngramSize': ngramSize,
                    'status': 'success'
                })
                
            except Exception as e:
                # Log failure
                log_df = update_run_log(log_path, log_df, {
                    'target_id': target_id,
                    'reference_id': reference_id,
                    'timestamp': datetime.now().isoformat(),
                    'match_count': 0,
                    'threshold': threshold,
                    'cutoff': cutoff,
                    'ngramSize': ngramSize,
                    'status': f'error: {str(e)}'
                })
                continue

        # Periodically save results during the run for a single target
        os.makedirs(os.path.dirname(results_path), exist_ok=True)
        with open(results_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nFlexible Analysis complete. Total {len(results)} matches found across all targets.")

if __name__ == "__main__":
    # Parameters for the analysis
    THRESHOLD = 2
    CUTOFF = 4
    NGRAM_SIZE = 3
    
    run_flexible_analysis(
        target_dir='target_texts',
        reference_dir='reference_texts',
        results_path='results/flexible_matches.json',
        log_path='results/flexible_run_log.csv',
        threshold=THRESHOLD,
        cutoff=CUTOFF,
        ngramSize=NGRAM_SIZE
    )
