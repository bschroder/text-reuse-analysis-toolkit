import pandas as pd
import shutil
import os

def copy_matches(log_path, src_dir, dst_dir):
    if not os.path.exists(log_path):
        print(f"Log file {log_path} not found.")
        return

    os.makedirs(dst_dir, exist_ok=True)
    df = pd.read_csv(log_path)
    
    # Filter for works with at least one match
    matches = df[df['match_count'] > 0]
    print(f"Found {len(matches)} works with matches.")
    
    copy_count = 0
    for _, row in matches.iterrows():
        ref_id = row['reference_id']
        src_path = os.path.join(src_dir, f"{ref_id}.txt")
        dst_path = os.path.join(dst_dir, f"{ref_id}.txt")
        
        if os.path.exists(src_path):
            shutil.copy2(src_path, dst_path)
            copy_count += 1
        else:
            print(f"Warning: Source file {src_path} not found.")

    print(f"Successfully copied {copy_count} files to {dst_dir}.")

if __name__ == "__main__":
    copy_matches('results/flexible_run_log.csv', 'reference_texts', 'reference_texts_with_matches')
