import redis
import json
import os
import sys

# --- Configuration ---
# IMPORTANT: Change this to the ID of the job you want to fix.
JOB_ID_TO_FIX = "job-20250813052520339" 

# --- Script ---
# Add the project's root directory to the Python path to allow importing 'app'
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

# Now we can import the settings
from backend.app.config import settings

def fix_job_result_in_redis(job_id: str):
    """
    Reads the correct result JSON from the filesystem and updates the
    corresponding job status key in Redis to fix a corrupted entry.
    """
    print(f"Attempting to fix result for job: {job_id}")

    # 1. Construct the path to the correct result file
    result_filename = "stage4_h3_anomaly.json"
    result_filepath = os.path.join(settings.RESULTS_DIR, job_id, result_filename)

    if not os.path.exists(result_filepath):
        print(f"Error: Result file not found at {result_filepath}")
        return

    print(f"Found result file: {result_filepath}")

    # 2. Read the correct result data from the file
    try:
        with open(result_filepath, 'r') as f:
            correct_result_data = json.load(f)
        print("Successfully read and parsed the result file.")
    except Exception as e:
        print(f"Error reading or parsing JSON file: {e}")
        return

    # 3. Construct the final status object that *should* have been saved
    final_status_object = {
        "status": "completed",
        "results": {
            "stage4_h3_anomaly": correct_result_data
        }
    }
    final_status_json = json.dumps(final_status_object)
    print("Constructed the correct final status object.")

    # 4. Connect to Redis and update the key
    try:
        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        redis_key = f"job_status:{job_id}"
        
        print(f"Connecting to Redis and setting key '{redis_key}'...")
        redis_client.set(redis_key, final_status_json)
        
        # Verify the key was set
        updated_value = redis_client.get(redis_key)
        if updated_value == final_status_json:
            print("\nSuccess! The job result has been fixed in Redis.")
            print("You should now be able to refresh the viewer page for this job.")
        else:
            print("\nError: Failed to verify the updated value in Redis.")
            
    except Exception as e:
        print(f"An error occurred while connecting to or updating Redis: {e}")

if __name__ == "__main__":
    if not JOB_ID_TO_FIX or "your_job_id_here" in JOB_ID_TO_FIX:
        print("Please edit this script and set the JOB_ID_TO_FIX variable.")
    else:
        fix_job_result_in_redis(JOB_ID_TO_FIX)
