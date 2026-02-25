"""Power Platform CLI integration"""
import asyncio
import subprocess
from pathlib import Path
from typing import Tuple, Optional
import logging
import config

logger = logging.getLogger(__name__)


async def check_pac_cli_available() -> bool:
    """
    Check if pac CLI is installed and available (either traditional pac or dnx)
    
    Returns:
        True if pac CLI is available
    """
    # First try traditional pac command
    try:
        proc = await asyncio.create_subprocess_exec(
            config.PAC_CLI_COMMAND,
            "help",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0:
            return True
    except (FileNotFoundError, asyncio.TimeoutError, Exception):
        pass
    
    # Try dnx approach (requires .NET 10+)
    # First check if we have .NET 10+
    try:
        proc = await asyncio.create_subprocess_exec(
            "dotnet",
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        version = stdout.decode('utf-8').strip()
        major_version = int(version.split('.')[0])
        
        if major_version >= 10:
            # .NET 10+ is available, assume dnx will work
            # We don't actually run dnx here because it's slow on first run
            return True
    except (FileNotFoundError, asyncio.TimeoutError, ValueError, Exception):
        pass
    
    return False


async def unpack_msapp(msapp_path: Path, output_dir: Path) -> Tuple[bool, Optional[str]]:
    """
    Unpack a .msapp file using pac canvas unpack
    
    Args:
        msapp_path: Path to the .msapp file
        output_dir: Directory to unpack to
    
    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Build command: pac canvas unpack --msapp <path> --sources <output>
        # Support both pac and dnx approaches
        if config.USE_DNX:
            cmd = config.DNX_COMMAND + [
                "canvas",
                "unpack",
                "--msapp", str(msapp_path),
                "--sources", str(output_dir)
            ]
        else:
            cmd = [
                config.PAC_CLI_COMMAND,
                "canvas",
                "unpack",
                "--msapp", str(msapp_path),
                "--sources", str(output_dir)
            ]
        
        logger.info(f"Unpacking {msapp_path.name} to {output_dir}")
        
        # Execute command
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(msapp_path.parent)
        )
        
        # Wait with timeout
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=config.PAC_UNPACK_TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            return False, "Unpack operation timed out"
        
        if proc.returncode == 0:
            logger.info(f"Successfully unpacked {msapp_path.name}")
            return True, None
        else:
            error_msg = stderr.decode('utf-8', errors='replace')
            logger.error(f"Failed to unpack {msapp_path.name}: {error_msg}")
            return False, error_msg
            
    except Exception as e:
        logger.exception(f"Error unpacking {msapp_path.name}")
        return False, str(e)


async def unpack_all_msapps(msapp_files: list[Path], base_output_dir: Path) -> dict[str, Tuple[bool, Optional[str]]]:
    """
    Unpack multiple .msapp files concurrently
    
    Args:
        msapp_files: List of .msapp file paths
        base_output_dir: Base directory for unpacked outputs
    
    Returns:
        Dictionary mapping app names to (success, error_message) tuples
    """
    results = {}
    
    # Create tasks for concurrent unpacking
    tasks = []
    for msapp_file in msapp_files:
        app_name = msapp_file.stem
        output_dir = base_output_dir / f"{app_name}_src"
        tasks.append((app_name, unpack_msapp(msapp_file, output_dir)))
    
    # Run all unpacking operations concurrently
    for app_name, task in tasks:
        success, error = await task
        results[app_name] = (success, error)
    
    return results


def get_pac_cli_version() -> Optional[str]:
    """
    Get the version of pac CLI installed
    
    Returns:
        Version string or None if not available
    """
    try:
        result = subprocess.run(
            [config.PAC_CLI_COMMAND],
            capture_output=True,
            text=True,
            timeout=10
        )
        # PAC CLI shows version in help output
        output = result.stdout + result.stderr
        if "Microsoft PowerPlatform CLI" in output:
            # Extract version line
            for line in output.split('\n'):
                if 'Version:' in line:
                    return line.strip()
            return "Microsoft PowerPlatform CLI (version info not parsed)"
        return None
    except Exception:
        return None
