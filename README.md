# 🧪 SWE-bench Data Point Validator

A comprehensive validation system for SWE-bench data points with automated CI/CD integration.

## 📋 Overview

This project provides automated validation of SWE-bench data points using the official SWE-bench evaluation harness. It includes a command-line validator, GitHub Actions integration, and detailed error reporting to ensure data quality.

## 🚀 Features

- ✅ **Official SWE-bench Integration**: Uses `swebench.harness.run_evaluation` with `run_instance()`
- ✅ **Docker-based Validation**: Isolated test execution environment
- ✅ **GitHub Actions CI/CD**: Automatic validation on PR/push
- ✅ **Comprehensive Error Reporting**: Detailed validation failure diagnostics
- ✅ **Batch Processing**: Validates multiple data points efficiently
- ✅ **Multiple Cache Levels**: Optimized performance with image caching

## 🏗️ Architecture

### Components

1. **`swe_bench_validator/`** - Core validation module
2. **`swe_bench_downloader/`** - Data point download utilities  
3. **`.github/workflows/`** - CI/CD automation
4. **`scripts/`** - Helper scripts and local testing tools
5. **`data_points/`** - Sample and test data points

### Docker Architecture

The system uses SWE-bench's 3-layer Docker architecture:
- **Base Image**: Common system dependencies
- **Environment Image**: Python environments and dependencies
- **Instance Image**: Repository-specific setup and patches

For detailed architecture documentation, see [swe-bench-docker-architecture.md](swe-bench-docker-architecture.md).

## 📦 Installation

### Prerequisites

- Python 3.8+
- Docker
- Git
- UV package manager (recommended) or pip

### Setup

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd swe_bench
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Verify installation:**
   ```bash
   python -m swe_bench_validator --help
   ```

5. **Docker Setup** (Required for full validation):
   ```bash
   # Ensure Docker is running
   docker --version
   
   # For full validation, SWE-bench environment images are needed
   # These can be built or downloaded (requires significant time/resources)
   # See Docker Architecture section for details
   ```

## 🔧 Usage

### Command Line Interface

#### Validate a single data point:
```bash
python -m swe_bench_validator --instance <instance_id>
```

#### Validate with verbose output:
```bash
python -m swe_bench_validator --instance <instance_id> --verbose
```

#### Validate multiple data points:
```bash
python -m swe_bench_validator --instances instance1 instance2 instance3
```

### Batch Validation Script

Validate changed data points (used by GitHub Actions):
```bash
export CHANGED_FILES="data_points/file1.json data_points/file2.json"
python scripts/validate_changed.py
```

### Local Testing

Test the complete workflow locally:
```bash
./scripts/test_workflow_locally.sh
```

Test all data points:
```bash
./scripts/test_workflow_locally.sh all
```

## 📊 Data Point Format

SWE-bench data points must include:

```json
{
  "repo": "owner/repository",
  "instance_id": "unique_identifier",
  "base_commit": "commit_hash",
  "patch": "diff --git a/file.py b/file.py\n...",
  "test_patch": "diff --git a/test_file.py b/test_file.py\n...",
  "problem_statement": "Description of the issue",
  "FAIL_TO_PASS": ["test::that::should::pass"],
  "PASS_TO_PASS": ["test::that::should::continue::passing"],
  "environment_setup_commit": "commit_hash"
}
```

### Required Fields

- `repo`: Repository in format `owner/repo`
- `instance_id`: Unique identifier
- `base_commit`: Git commit hash (minimum 7 characters)
- `patch`: Git patch in diff format
- `test_patch`: Test modifications in diff format
- `FAIL_TO_PASS`: Tests that should pass after applying patch
- `PASS_TO_PASS`: Tests that should continue passing

## 🤖 GitHub Actions Integration

### Automatic Validation

The system automatically validates data points when:
- New `.json` files are added to `data_points/`
- Existing data point files are modified
- Pull requests are created or updated

### Workflow Features

- **🔍 Smart Detection**: Only validates changed files
- **📝 PR Comments**: Posts validation results as PR comments
- **🚫 Branch Protection**: Blocks merging if validation fails
- **📊 Status Checks**: Clear pass/fail indicators
- **🐛 Error Reporting**: Detailed failure diagnostics

### Configuration

The workflow is defined in `.github/workflows/validate-datapoints.yml` and triggers on:
```yaml
on:
  push:
    paths: ['data_points/**/*.json']
  pull_request:
    paths: ['data_points/**/*.json']
```

## 🔍 Validation Process

### Validation Steps

1. **JSON Structure Validation**
   - Valid JSON syntax
   - Required fields present
   - Correct data types

2. **Content Validation**
   - Repository format (`owner/repo`)
   - Commit hash format (hex, 7+ characters)
   - Patch format (valid git diff)

3. **SWE-bench Harness Validation**
   - Docker environment setup
   - Repository cloning and setup
   - Patch application
   - Test execution
   - Result verification

### Error Categories

- **`INVALID_JSON`**: Malformed JSON syntax
- **`FILE_NOT_FOUND`**: Missing data point file
- **`READ_ERROR`**: File access issues
- **`FAILED`**: SWE-bench validation failure
- **`TIMEOUT`**: Validation exceeded time limit
- **`ERROR`**: Unexpected errors

## 📈 Performance Optimization

### Cache Levels

| Level | Description | Disk Usage | Speed |
|-------|-------------|------------|-------|
| `none` | No caching | ~120GB during execution | Slowest |
| `base` | Base image only | ~120GB during execution | Slow |
| `env` | Base + environment | ~500GB | Fast |
| `instance` | All images | ~2,000GB | Fastest |

### Configuration

Set cache level in environment:
```bash
export SWE_BENCH_CACHE_LEVEL=env  # Recommended for CI/CD
```

## 🧪 Testing

### Sample Data Points

The repository includes sample data points:
- `data_points/astropy__astropy-11693.json` - Valid example
- `data_points/astropy__astropy-11693-fail.json` - Edge case example

### Negative Testing

For comprehensive testing, see [NEGATIVE_TESTING_REPORT.md](NEGATIVE_TESTING_REPORT.md) which includes:
- Invalid JSON syntax
- Missing required fields  
- Invalid patch formats
- Repository access issues

### Local Testing Commands

```bash
# Test single data point
python -m swe_bench_validator --instance astropy__astropy-11693 --verbose

# Test validation script
CHANGED_FILES="data_points/astropy__astropy-11693.json" python scripts/validate_changed.py

# Test complete workflow
./scripts/test_workflow_locally.sh
```

## 🚨 Troubleshooting

### Common Issues

1. **Docker not running**
   ```bash
   sudo systemctl start docker  # Linux
   # or start Docker Desktop
   ```

2. **Permission denied**
   ```bash
   sudo usermod -aG docker $USER
   # Log out and back in
   ```

3. **Memory issues**
   - Increase Docker memory limit to 8GB+
   - Use `base` cache level instead of `env`

4. **Network timeouts**
   - Check internet connection
   - Increase timeout values
   - Retry validation

### Debug Mode

Enable verbose logging:
```bash
export DEBUG=1
python -m swe_bench_validator --instance <id> --verbose
```

### Log Files

Validation logs are stored in:
```
logs/
├── build/
│   ├── base/           # Base image build logs
│   ├── env/            # Environment image build logs
│   └── instances/      # Instance image build logs
└── run_evaluation/     # Evaluation execution logs
```

## 📚 Documentation

- [Implementation Plan](IMPLEMENTATION_PLAN.md) - Development roadmap
- [Docker Architecture](swe-bench-docker-architecture.md) - Technical architecture
- [Negative Testing Report](NEGATIVE_TESTING_REPORT.md) - Test results

## 🤝 Contributing

### Adding New Data Points

1. Create JSON file in `data_points/`
2. Follow the required format
3. Create pull request
4. Wait for automatic validation
5. Address any validation failures

### Development

1. Fork the repository
2. Create feature branch
3. Make changes
4. Add tests if applicable  
5. Ensure all validations pass
6. Submit pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔗 Related Projects

- [SWE-bench](https://github.com/princeton-nlp/SWE-bench) - Official SWE-bench repository
- [SWE-bench Library](https://pypi.org/project/swebench/) - Python package

## 📞 Support

For issues and questions:
1. Check existing [Issues](../../issues)
2. Review [Troubleshooting](#-troubleshooting) section
3. Create new issue with:
   - Error message
   - Steps to reproduce
   - System information
   - Log files (if applicable)

---

**Built with ❤️ for the SWE-bench community**