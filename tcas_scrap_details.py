import requests
import csv
import json
import concurrent.futures
import os

COURSES_URL = "https://my-tcas.s3.ap-southeast-1.amazonaws.com/mytcas/courses.json?ts=19eba80224a"
DETAIL_URL_TEMPLATE = "https://my-tcas.s3.ap-southeast-1.amazonaws.com/mytcas/ly-programs/{}.json?state=update-prediction-v2"
DS_CSV_FILENAME = "TCAS69-R3-MinMax-10June26.csv"

def get_ds_scores_mapping():
    print(f"Reading {DS_CSV_FILENAME} to map max DS and min DS...")
    ds_mapping = {}
    
    if not os.path.exists(DS_CSV_FILENAME):
        print(f"Warning: {DS_CSV_FILENAME} not found. DS scores will be empty.")
        return ds_mapping
        
    with open(DS_CSV_FILENAME, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid = row.get("program id", "").strip()
            if pid:
                ds_mapping[pid] = {
                    "max_ds": row.get("max DS", ""),
                    "min_ds": row.get("min DS", "")
                }
    return ds_mapping

def get_courses_mapping(ds_mapping):
    print("Fetching courses.json to map universities, faculties, and campuses...")
    resp = requests.get(COURSES_URL)
    resp.raise_for_status()
    courses = resp.json()
    
    mapping = {}
    for c in courses:
        pid = c.get("program_id")
        if pid:
            mapping[pid] = {
                "university": c.get("university_name_th", ""),
                "faculty": c.get("faculty_name_th", ""),
                "campus": c.get("campus_name_th", ""),
                "max_ds": ds_mapping.get(pid, {}).get("max_ds", ""),
                "min_ds": ds_mapping.get(pid, {}).get("min_ds", "")
            }
    return mapping

def fetch_program_detail(program_id, mapping_info):
    url = DETAIL_URL_TEMPLATE.format(program_id)
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = []
            
            for item in data:
                # Filter only Round 3 (Admission)
                project_name = item.get("project_name_th", "")
                if "Admission" not in project_name and "3" not in project_name:
                    continue
                
                major = item.get("major_name_th", "").strip()
                if not major:
                    major = item.get("program_name_th", "")
                
                program_name = item.get("program_name_th", "").strip()
                campus = mapping_info.get("campus", "").strip()
                
                if campus:
                    program_name = f"{program_name} {campus}".strip()
                
                score_weight = item.get("scores", {})
                score_weight_str = json.dumps(score_weight, ensure_ascii=False)
                
                record = {
                    "program_id": program_id,
                    "project_name": project_name,
                    "university": mapping_info["university"],
                    "faculty": mapping_info["faculty"],
                    "major": major,
                    "program_name": program_name,
                    "score_weight": score_weight_str,
                    "min_score": item.get("min_score", ""),
                    "max_score": item.get("max_score", ""),
                    "min_score_ds": mapping_info.get("min_ds", ""),
                    "max_score_ds": mapping_info.get("max_ds", "")
                }
                results.append(record)
            return results
        else:
            return []
    except Exception as e:
        return []

def main():
    ds_mapping = get_ds_scores_mapping()
    mapping = get_courses_mapping(ds_mapping)
    program_ids = list(mapping.keys())
    
    print(f"Total programs to fetch details for: {len(program_ids)}")
    print("Starting concurrent fetching (this may take a minute or two)...")
    
    all_details = []
    completed = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        future_to_pid = {
            executor.submit(fetch_program_detail, pid, mapping[pid]): pid 
            for pid in program_ids
        }
        
        for future in concurrent.futures.as_completed(future_to_pid):
            try:
                data = future.result()
                if data:
                    all_details.extend(data)
            except Exception as e:
                pass
                
            completed += 1
            if completed % 500 == 0:
                print(f"Processed {completed}/{len(program_ids)} programs...")
                
    output_filename = "program_details.csv"
    output_json = "program_details.json"
    
    if all_details:
        print(f"Saving to {output_filename}...")
        headers = list(all_details[0].keys())
        
        with open(output_filename, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(all_details)
            
        print(f"Saving to {output_json}...")
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(all_details, f, ensure_ascii=False, indent=4)
            
        print(f"\nDone! Successfully saved {len(all_details)} admission projects to {output_filename} and {output_json}")
    else:
        print("\nNo data to save.")

if __name__ == "__main__":
    main()
