from importlib import metadata

try:
    APP_VERSION = metadata.version("o-qt-mcp-server")
except metadata.PackageNotFoundError:
    APP_VERSION = "0.3.1"
