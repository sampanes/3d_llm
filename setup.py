from setuptools import setup, find_packages

setup(
    name="3d-llm",
    version="0.1.0",
    description="AI-Assisted STL Generation for 3D Printing",
    author="Sampanes",
    python_requires=">=3.10",
    packages=find_packages(),
    py_modules=["scripts"],
    install_requires=[
        line.strip()
        for line in open("requirements.txt")
        if line.strip() and not line.startswith("#")
    ],
    entry_points={
        "console_scripts": [
            "3d-llm=scripts.generate:main",
        ],
    },
)
