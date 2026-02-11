"""
Setup script for playnite_python.
"""

from setuptools import setup, find_packages

setup(
    name="playnite_python",
    version="1.0.0",
    description="Modern Python game library manager — replacing the legacy C# Playnite application.",
    author="Playnite Python Contributors",
    python_requires=">=3.10",
    packages=find_packages(where="."),
    install_requires=[
        "click>=8.1.0",
        "PyYAML>=6.0",
    ],
    extras_require={
        "marketplace": ["requests>=2.28.0"],
        "monitor": ["psutil>=5.9.0"],
        "all": ["requests>=2.28.0", "psutil>=5.9.0"],
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "playnite=playnite_python.cli.main:cli",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Games/Entertainment",
    ],
)
