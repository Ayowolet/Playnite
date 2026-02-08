"""Setup script for Playnite Python."""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README
readme_path = Path(__file__).parent / "PYTHON_README.md"
if readme_path.exists():
    long_description = readme_path.read_text(encoding="utf-8")
else:
    long_description = "Modern Game Library Manager with headless architecture"

# Read requirements
requirements_path = Path(__file__).parent / "requirements.txt"
if requirements_path.exists():
    requirements = requirements_path.read_text().strip().split('\n')
    requirements = [r.strip() for r in requirements if r.strip() and not r.startswith('#')]
else:
    requirements = [
        'sqlalchemy>=2.0.0',
        'click>=8.1.0',
        'pygame>=2.5.0',
        'pyyaml>=6.0',
    ]

setup(
    name='playnite-python',
    version='0.1.0',
    description='Modern Game Library Manager with headless controller input and advanced organisation',
    long_description=long_description,
    long_description_content_type='text/markdown',
    author='Playnite Python Team',
    python_requires='>=3.8',
    packages=find_packages(exclude=['tests', 'tests.*']),
    install_requires=requirements,
    extras_require={
        'dev': [
            'pytest>=7.4.0',
            'pytest-cov>=4.1.0',
            'black>=23.0.0',
            'flake8>=6.0.0',
            'mypy>=1.0.0',
        ]
    },
    entry_points={
        'console_scripts': [
            'playnite=playnite_py.cli.main:cli',
        ],
    },
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: End Users/Desktop',
        'Topic :: Games/Entertainment',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
    keywords='game library manager controller input headless',
    project_urls={
        'Documentation': 'https://github.com/yourusername/playnite-python',
        'Source': 'https://github.com/yourusername/playnite-python',
        'Tracker': 'https://github.com/yourusername/playnite-python/issues',
    },
)
