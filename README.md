# Job Restart Manager

A simple, robust solution for managing and restarting failed rsync backup jobs.

## Features

- ✅ **Failed Job Detection** - Automatically identifies failed backup jobs
- ✅ **One-Click Restart** - Restart individual failed jobs with retry logic
- ✅ **Bulk Restart** - Restart all failed jobs at once
- ✅ **Progress Tracking** - Real-time progress updates during job execution
- ✅ **Retry Logic** - Exponential backoff with configurable retry limits
- ✅ **Command Builder** - Visual rsync command building with preview
- ✅ **Job Logging** - Detailed logs for each job execution
- ✅ **Simple Web UI** - Clean, responsive interface

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application:**
   ```bash
   python app.py
   ```

3. **Open in browser:**
   Navigate to http://localhost:5000

## Usage

### Creating Jobs
1. Click "Create New Job"
2. Fill in source/destination paths
3. Configure rsync options
4. Preview command and create job

### Managing Failed Jobs
- **Individual Restart**: Click "🔄 Restart" on any failed job
- **Bulk Restart**: Click "🔄 Restart All Failed Jobs"
- **View Logs**: Click "📋 Logs" to see detailed execution logs

### Job Status
- **Failed**: Red status, can be restarted
- **Running**: Blue status, shows progress bar
- **Completed**: Green status, finished successfully
- **Stopped**: Yellow status, manually stopped

## Architecture

- **Backend**: Simple Flask application
- **Storage**: JSON-based job storage
- **Execution**: Subprocess-based rsync with retry logic
- **Frontend**: Vanilla JavaScript with real-time updates
- **Progress**: Server-Sent Events for live updates

## File Structure

```
job-restart-manager/
├── app.py              # Flask web application
├── job_storage.py       # JSON-based job storage
├── job_executor.py      # Job execution with retry logic
├── rsync_builder.py     # Rsync command builder
├── templates/
│   └── index.html      # Main web interface
├── static/
│   ├── style.css        # CSS styles
│   └── script.js       # JavaScript functionality
├── logs/               # Job execution logs
├── jobs.json          # Job storage file
└── requirements.txt    # Python dependencies
```

## Configuration

Jobs are stored in `jobs.json`. Each job includes:
- Basic info (name, source, destination)
- Rsync arguments (archive, compress, delete, etc.)
- Retry settings (max_retries, current retry_count)
- Status and progress tracking
- Error messages and logs

## Retry Logic

- **Exponential Backoff**: 1s, 2s, 4s, 8s, 16s, max 60s
- **Max Retries**: Configurable per job (default: 5)
- **Network Errors**: Automatically retried on connection issues
- **Manual Restart**: Reset retry count and start fresh

## Safety Features

- **Command Validation**: Validates rsync arguments before execution
- **Path Safety**: Basic path traversal protection
- **Confirmation Dialogs**: Required for destructive operations
- **Error Logging**: All failures logged with details
- **Graceful Stops**: Clean process termination

## API Endpoints

- `GET /api/jobs` - List all jobs
- `GET /api/jobs/failed` - List failed jobs
- `POST /api/job/create` - Create new job
- `POST /api/job/<id>/start` - Start job
- `POST /api/job/<id>/stop` - Stop job
- `POST /api/job/<id>/restart` - Restart failed job
- `POST /api/jobs/restart-failed` - Restart all failed jobs
- `DELETE /api/job/<id>/delete` - Delete job
- `GET /api/job/<id>/logs` - Get job logs
- `POST /api/rsync/preview` - Preview rsync command

## Development

The application is designed to be simple and robust:
- **No external dependencies** beyond Flask
- **JSON storage** - no database setup required
- **Simple deployment** - single Python file
- **Clear error messages** - easy debugging
- **Responsive design** - works on mobile and desktop

## License

MIT License - feel free to use and modify.
