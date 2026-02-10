from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="playnite-python",
    version="1.0.0",
    author="Playnite Python Team",
    description="Python integration for Playnite - Game recommendations and media capture",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/playnite-python",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Games/Entertainment",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
    ],
    python_requires=">=3.8",
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "pydantic>=2.5.0",
        "scikit-learn>=1.4.0",
        "pandas>=2.2.0",
        "numpy>=1.26.0",
        "opencv-python>=4.9.0",
        "Pillow>=10.2.0",
        "mss>=9.0.0",
        "pynput>=1.7.6",
        "sqlalchemy>=2.0.25",
        "python-dotenv>=1.0.0",
        "loguru>=0.7.2",
        "httpx>=0.26.0",
        "typer>=0.9.0",
        "rich>=13.7.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-asyncio>=0.23.0",
            "pytest-cov>=4.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "playnite-python=playnite_python.__main__:main",
        ],
    },
)
