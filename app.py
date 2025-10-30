"""
Simple Flask web application for job restart manager
"""
from flask import Flask, render_template, request, jsonify, redirect, url_for
import json
from datetime import datetime
from job_storage import JobStorage
from job_executor import JobExecutor
from rsync_builder import get_default_rsync_args, validate_rsync_args
from rclone_storage import RcloneStorage
from rclone_executor import RcloneExecutor
from rclone_config import RcloneConfig
from rclone_builder import get_default_rclone_args, validate_rclone_args


app = Flask(__name__)

# Initialize components
storage = JobStorage()
executor = JobExecutor(storage)

# Initialize rclone components
rclone_storage = RcloneStorage()
rclone_executor = RcloneExecutor(rclone_storage)
rclone_config = RcloneConfig()


@app.route('/')
def index():
    """Main page with job list"""
    jobs = storage.get_all_jobs()
    failed_jobs = storage.get_failed_jobs()
    running_jobs = executor.get_running_jobs()
    
    return render_template('index.html', 
                      jobs=jobs, 
                      failed_jobs=failed_jobs,
                      running_jobs=running_jobs)


@app.route('/api/jobs')
def api_jobs():
    """API endpoint to get all jobs"""
    jobs = storage.get_all_jobs()
    return jsonify({"jobs": jobs})


@app.route('/api/jobs/failed')
def api_failed_jobs():
    """API endpoint to get failed jobs"""
    jobs = storage.get_failed_jobs()
    return jsonify({"jobs": jobs})


@app.route('/api/job/<job_id>')
def api_job(job_id):
    """API endpoint to get specific job"""
    job = storage.get_job(job_id)
    if job:
        return jsonify(job)
    return jsonify({"error": "Job not found"}), 404


@app.route('/api/job/create', methods=['POST'])
def api_create_job():
    """API endpoint to create new job"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name') or not data.get('source') or not data.get('destination'):
            return jsonify({"error": "Name, source, and destination are required"}), 400
        
        # Create job with default rsync args
        job_data = {
            "name": data['name'],
            "source": data['source'],
            "destination": data['destination'],
            "rsync_args": data.get('rsync_args', get_default_rsync_args()),
            "excludes": data.get('excludes', ''),
            "max_retries": data.get('max_retries', 5)
        }
        
        job_id = storage.create_job(job_data)
        
        return jsonify({"job_id": job_id, "message": "Job created successfully"})
        
    except Exception as e:
        return jsonify({"error": f"Failed to create job: {str(e)}"}), 500


@app.route('/api/job/<job_id>/start', methods=['POST'])
def api_start_job(job_id):
    """API endpoint to start a job"""
    try:
        if executor.start_job(job_id):
            return jsonify({"message": f"Job {job_id} started successfully"})
        else:
            return jsonify({"error": f"Failed to start job {job_id}"}), 400
            
    except Exception as e:
        return jsonify({"error": f"Failed to start job: {str(e)}"}), 500


@app.route('/api/job/<job_id>/stop', methods=['POST'])
def api_stop_job(job_id):
    """API endpoint to stop a job"""
    try:
        if executor.stop_job(job_id):
            return jsonify({"message": f"Job {job_id} stopped successfully"})
        else:
            return jsonify({"error": f"Failed to stop job {job_id}"}), 400
            
    except Exception as e:
        return jsonify({"error": f"Failed to stop job: {str(e)}"}), 500


@app.route('/api/job/<job_id>/restart', methods=['POST'])
def api_restart_job(job_id):
    """API endpoint to restart a failed job"""
    try:
        # Reset job status to allow restart
        storage.update_job(job_id, {"status": "pending_restart"})
        
        if executor.start_job(job_id):
            return jsonify({"message": f"Job {job_id} restarted successfully"})
        else:
            return jsonify({"error": f"Failed to restart job {job_id}"}), 400
            
    except Exception as e:
        return jsonify({"error": f"Failed to restart job: {str(e)}"}), 500


@app.route('/api/jobs/restart-failed', methods=['POST'])
def api_restart_failed_jobs():
    """API endpoint to restart all failed jobs"""
    try:
        restarted_count = executor.restart_failed_jobs()
        return jsonify({
            "message": f"Restarted {restarted_count} failed jobs",
            "restarted_count": restarted_count
        })
        
    except Exception as e:
        return jsonify({"error": f"Failed to restart jobs: {str(e)}"}), 500


@app.route('/api/job/<job_id>/delete', methods=['DELETE'])
def api_delete_job(job_id):
    """API endpoint to delete a job"""
    try:
        # Stop job if running
        if executor.is_job_running(job_id):
            executor.stop_job(job_id)
        
        # Delete job
        storage.delete_job(job_id)
        
        return jsonify({"message": f"Job {job_id} deleted successfully"})
        
    except Exception as e:
        return jsonify({"error": f"Failed to delete job: {str(e)}"}), 500


@app.route('/api/job/<job_id>/logs')
def api_job_logs(job_id):
    """API endpoint to get job logs"""
    try:
        log_file = executor._get_log_file(job_id)
        if log_file.exists():
            with open(log_file, 'r') as f:
                logs = f.read()
            return jsonify({"logs": logs})
        else:
            return jsonify({"logs": ""})
            
    except Exception as e:
        return jsonify({"error": f"Failed to read logs: {str(e)}"}), 500


@app.route('/api/rsync/preview', methods=['POST'])
def api_rsync_preview():
    """API endpoint to preview rsync command"""
    try:
        data = request.get_json()
        
        source = data.get('source', '')
        destination = data.get('destination', '')
        rsync_args = data.get('rsync_args', {})
        excludes = data.get('excludes', '')
        
        # Validate arguments
        errors = validate_rsync_args({
            'source': source,
            'destination': destination,
            **rsync_args
        })
        
        if errors:
            return jsonify({"errors": errors})
        
        # Build command string
        from rsync_builder import build_rsync_command_string
        command = build_rsync_command_string(source, destination, rsync_args, excludes)
        
        return jsonify({
            "command": command,
            "errors": []
        })
        
    except Exception as e:
        return jsonify({"error": f"Failed to build command: {str(e)}"}), 500


# WebSocket-like progress updates (using Server-Sent Events)
@app.route('/api/progress')
def progress_stream():
    """Stream job progress updates"""
    def generate():
        while True:
            # Get running jobs and their progress
            running_jobs = executor.get_running_jobs()
            progress_data = []
            
            for job_id in running_jobs:
                job = storage.get_job(job_id)
                if job and 'progress' in job:
                    progress_data.append({
                        'job_id': job_id,
                        'progress': job['progress']
                    })
            
            if progress_data:
                yield f"data: {json.dumps(progress_data)}\n\n"
            
            # Send update every 2 seconds
            import time
            time.sleep(2)
    
    return app.response_class(generate(), mimetype='text/plain')


# ==================== RCLONE API ENDPOINTS ====================

@app.route('/api/rclone/status')
def api_rclone_status():
    """Get rclone installation status"""
    is_installed = rclone_config.is_rclone_installed()
    version = rclone_config.get_rclone_version() if is_installed else None
    
    return jsonify({
        "installed": is_installed,
        "version": version
    })


@app.route('/api/rclone/operations')
def api_rclone_operations():
    """Get all rclone operations"""
    operations = rclone_storage.get_all_operations()
    return jsonify({"operations": operations})


@app.route('/api/rclone/operation/<operation_id>')
def api_rclone_operation(operation_id):
    """Get specific rclone operation"""
    operation = rclone_storage.get_operation(operation_id)
    if operation:
        return jsonify(operation)
    return jsonify({"error": "Operation not found"}), 404


@app.route('/api/rclone/operation', methods=['POST'])
def api_create_rclone_operation():
    """Create new rclone operation"""
    try:
        data = request.get_json()
        
        # Validate required fields
        if not data.get('name') or not data.get('source') or not data.get('destination'):
            return jsonify({"error": "Name, source, and destination are required"}), 400
        
        if not data.get('operation_type'):
            return jsonify({"error": "Operation type is required"}), 400
        
        # Create operation with default rclone args
        operation_data = {
            "name": data['name'],
            "source": data['source'],
            "destination": data['destination'],
            "operation_type": data['operation_type'],
            "rclone_args": data.get('rclone_args', get_default_rclone_args()),
            "excludes": data.get('excludes', ''),
            "max_retries": data.get('max_retries', 3)
        }
        
        operation_id = rclone_storage.create_operation(operation_data)
        rclone_executor.start_operation(operation_id)
        
        return jsonify({"operation_id": operation_id, "message": "Operation created and started"})
        
    except Exception as e:
        return jsonify({"error": f"Failed to create operation: {str(e)}"}), 500


@app.route('/api/rclone/operation/<operation_id>/start', methods=['POST'])
def api_start_rclone_operation(operation_id):
    """Start a rclone operation"""
    try:
        if rclone_executor.start_operation(operation_id):
            return jsonify({"message": f"Operation {operation_id} started successfully"})
        else:
            return jsonify({"error": f"Failed to start operation {operation_id}"}), 400
            
    except Exception as e:
        return jsonify({"error": f"Failed to start operation: {str(e)}"}), 500


@app.route('/api/rclone/operation/<operation_id>/stop', methods=['POST'])
def api_stop_rclone_operation(operation_id):
    """Stop a running rclone operation"""
    try:
        if rclone_executor.stop_operation(operation_id):
            return jsonify({"message": f"Operation {operation_id} stopped successfully"})
        else:
            return jsonify({"error": f"Failed to stop operation {operation_id}"}), 400
            
    except Exception as e:
        return jsonify({"error": f"Failed to stop operation: {str(e)}"}), 500


@app.route('/api/rclone/operation/<operation_id>/delete', methods=['DELETE'])
def api_delete_rclone_operation(operation_id):
    """Delete a rclone operation"""
    try:
        # Stop if running
        if rclone_executor.is_operation_running(operation_id):
            rclone_executor.stop_operation(operation_id)
        
        # Delete operation
        rclone_storage.delete_operation(operation_id)
        
        return jsonify({"message": f"Operation {operation_id} deleted successfully"})
        
    except Exception as e:
        return jsonify({"error": f"Failed to delete operation: {str(e)}"}), 500


@app.route('/api/rclone/operation/<operation_id>/logs')
def api_rclone_operation_logs(operation_id):
    """Get rclone operation logs"""
    try:
        log_file = rclone_executor._get_log_file(operation_id)
        if log_file.exists():
            with open(log_file, 'r') as f:
                logs = f.read()
            return jsonify({"logs": logs})
        else:
            return jsonify({"logs": ""})
            
    except Exception as e:
        return jsonify({"error": f"Failed to read logs: {str(e)}"}), 500


@app.route('/api/rclone/remotes')
def api_rclone_remotes():
    """Get configured rclone remotes"""
    remotes = rclone_storage.get_all_remotes()
    system_remotes = rclone_config.list_remotes()
    
    return jsonify({
        "remotes": remotes,
        "system_remotes": system_remotes
    })


@app.route('/api/rclone/remote/<remote_name>/test', methods=['POST'])
def api_test_rclone_remote(remote_name):
    """Test remote connection"""
    try:
        result = rclone_config.test_remote(remote_name)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/rclone/backends')
def api_rclone_backends():
    """Get list of supported rclone backends"""
    backends = rclone_config.supported_backends()
    return jsonify({"backends": backends})


@app.route('/api/rclone/remote', methods=['POST'])
def api_add_rclone_remote():
    """Add new rclone remote"""
    try:
        data = request.get_json()
        
        if not data.get('name'):
            return jsonify({"error": "Remote name is required"}), 400
        
        remote_name = rclone_storage.add_remote(data)
        return jsonify({"remote_name": remote_name, "message": "Remote added successfully"})
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to add remote: {str(e)}"}), 500


@app.route('/api/rclone/remote/<remote_name>', methods=['DELETE'])
def api_delete_rclone_remote(remote_name):
    """Delete rclone remote"""
    try:
        rclone_storage.delete_remote(remote_name)
        return jsonify({"message": f"Remote '{remote_name}' deleted successfully"})
        
    except Exception as e:
        return jsonify({"error": f"Failed to delete remote: {str(e)}"}), 500


@app.route('/api/rclone/preview', methods=['POST'])
def api_rclone_preview():
    """Preview rclone command"""
    try:
        data = request.get_json()
        
        operation_type = data.get('operation_type', 'copy')
        source = data.get('source', '')
        destination = data.get('destination', '')
        rclone_args = data.get('rclone_args', {})
        excludes = data.get('excludes', '')
        
        # Validate arguments
        errors = validate_rclone_args({
            'source': source,
            'destination': destination,
            **rclone_args
        })
        
        if errors:
            return jsonify({"errors": errors})
        
        # Build command string
        from rclone_builder import build_rclone_command_string
        command = build_rclone_command_string(operation_type, source, destination, rclone_args, excludes)
        
        return jsonify({
            "command": command,
            "errors": []
        })
        
    except Exception as e:
        return jsonify({"error": f"Failed to build command: {str(e)}"}), 500


if __name__ == '__main__':
    # Create some sample jobs if none exist
    if not storage.get_all_jobs():
        sample_jobs = [
            {
                "name": "Documents Backup",
                "source": "/Users/aks/Documents",
                "destination": "/Volumes/Backup/Documents",
                "rsync_args": {
                    "archive": True,
                    "verbose": True,
                    "compress": True,
                    "delete": False
                },
                "excludes": ".DS_Store node_modules *.tmp",
                "status": "failed",
                "error_message": "Connection timed out",
                "retry_count": 2,
                "max_retries": 5
            },
            {
                "name": "Photos Sync", 
                "source": "/Users/aks/Photos",
                "destination": "/Volumes/Backup/Photos",
                "rsync_args": {
                    "archive": True,
                    "verbose": True,
                    "progress": True,
                    "delete": True
                },
                "excludes": ".DS_Store Thumbs.db",
                "status": "completed",
                "retry_count": 0,
                "max_retries": 3
            }
        ]
        
        for job_data in sample_jobs:
            storage.create_job(job_data)
        
        print("Created sample jobs for demonstration")
    
    print("Starting Job Restart Manager on http://localhost:8080")
    app.run(debug=True, host='0.0.0.0', port=8080)
