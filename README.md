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
   Navigate to http://localhost:8080

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

### Environment Variables

The application can be configured using the following environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_HOST` | `127.0.0.1` | Host address to bind to. Use `0.0.0.0` to allow external connections. |
| `FLASK_PORT` | `8080` | Port number for the web interface. |
| `FLASK_DEBUG` | `false` | Enable Flask debug mode. **WARNING: Never use in production!** |
| `DEMO_SEED` | `false` | Create sample demo jobs on first startup. |

**Example Usage:**

```bash
# Run on all interfaces with custom port
export FLASK_HOST=0.0.0.0
export FLASK_PORT=5000
python app.py

# Enable demo mode for testing
export DEMO_SEED=true
python app.py

# Enable debug mode (development only!)
export FLASK_DEBUG=true
python app.py
```

**Security Notes:**
- Never use `FLASK_DEBUG=true` in production environments
- Binding to `0.0.0.0` exposes the application to your network
- Consider using a reverse proxy (nginx, Apache) for production deployments

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

### Running Tests

The project includes comprehensive test suites to ensure code quality:

```bash
# Run all test suites
python test_sse.py                  # SSE endpoint tests
python test_status_strings.py       # Status enumeration tests
python test_validation.py           # Security and validation tests
python test_rclone_commands.py      # Command builder tests

# Run existing tests
python test_storage_safety.py       # Storage thread safety tests
python test_automation.py           # API integration tests
```

**Test Coverage:**
- **SSE Implementation**: Content type, headers, heartbeat behavior
- **Status Strings**: Enumeration, CSS class generation, JavaScript compatibility
- **Security**: Path traversal, dangerous paths, input validation
- **Command Building**: Rclone command generation, flag validation
- **Storage Safety**: Thread safety, atomic operations, data integrity
- **API Integration**: End-to-end functionality testing

### Exclude Patterns

When specifying exclude patterns for rsync, you can now use newline-separated patterns to handle patterns with spaces:

```
# Newline-separated (supports spaces in patterns)
My Documents/
*.tmp
node_modules

# Space-separated (legacy, no spaces in patterns)
*.tmp *.log .DS_Store
```

## License

MIT License - feel free to use and modify.
