#!/usr/bin/env python3
import os
import sys
import json
import logging
import re
import subprocess
from datetime import datetime, timezone

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/home/openclaw/.openclaw/workspace/logs/universal_cron.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def load_environment_vars(env_file):
    """Load environment variables from a file."""
    env = os.environ.copy()
    try:
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    try:
                        key, value = line.split('=', 1)
                        env[key.strip()] = value.strip().strip('"\'')
                    except ValueError:
                        logger.warning(f"Skipping invalid env line: {line}")
    except Exception as e:
        logger.error(f"Error loading environment file: {e}")
    return env

def parse_job_command(command):
    """Parse and clean complex job commands."""
    # Remove leading instruction text
    command = re.sub(r'^.*?:\s*', '', command)
    # Remove text in parentheses
    command = re.sub(r'\([^)]*\)', '', command)
    # Replace multiple whitespaces
    command = re.sub(r'\s+', ' ', command).strip()
    return command

def execute_shell_command(command, env, cwd):
    """Execute a shell command with comprehensive error handling."""
    try:
        result = subprocess.run(
            ['bash', '-c', command], 
            env=env, 
            capture_output=True, 
            text=True,
            cwd=cwd
        )
        
        if result.returncode == 0:
            logger.info(f"Command executed successfully")
            logger.info(f"STDOUT: {result.stdout}")
        else:
            logger.error(f"Command failed with return code {result.returncode}")
            logger.error(f"STDOUT: {result.stdout}")
            logger.error(f"STDERR: {result.stderr}")
        
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Exception executing command: {e}")
        return False

def main():
    """Main job runner logic."""
    logger.info("=" * 60)
    logger.info("UNIVERSAL CRON RUNNER START")
    logger.info(f"Current UTC Time: {datetime.now(timezone.utc)}")
    logger.info("=" * 60)
    
    # Paths
    WORKSPACE_DIR = "/home/openclaw/.openclaw/workspace"
    ENV_FILE = "/home/openclaw/.openclaw/cron/openclaw.env"
    JOBS_CONFIG = os.path.join(WORKSPACE_DIR, "cron", "jobs.json")
    
    # Load environment and job configuration
    try:
        env = load_environment_vars(ENV_FILE)
        
        with open(JOBS_CONFIG, 'r') as f:
            job_config = json.load(f)
    except Exception as e:
        logger.error(f"Configuration loading failed: {e}")
        sys.exit(1)
    
    # Track job execution
    successful_jobs = []
    failed_jobs = []
    
    # Execute enabled jobs
    for job in job_config.get('jobs', []):
        if job.get('enabled', False):
            job_name = job.get('name', 'unnamed_job')
            logger.info(f"Processing job: {job_name}")
            
            try:
                # Parse and clean command
                full_command = job['payload']['message']
                clean_command = parse_job_command(full_command)
                
                # Execute the job
                if execute_shell_command(clean_command, env, WORKSPACE_DIR):
                    successful_jobs.append(job_name)
                else:
                    failed_jobs.append(job_name)
            except Exception as e:
                logger.error(f"Job {job_name} processing failed: {e}")
                failed_jobs.append(job_name)
    
    # Final logging
    logger.info("=" * 60)
    logger.info("UNIVERSAL CRON RUNNER SUMMARY")
    logger.info(f"Successful Jobs: {successful_jobs}")
    logger.info(f"Failed Jobs: {failed_jobs}")
    logger.info("=" * 60)
    
    # Exit with non-zero code if any jobs failed
    sys.exit(0 if not failed_jobs else 1)

if __name__ == "__main__":
    main()