from setuptools import find_packages, setup


setup(
    name="camera-timelapse-controller",
    version="0.1.0",
    description="Control bracketed timelapse capture through gPhoto2.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    python_requires=">=3.9",
    packages=find_packages(include=["gphoto_timelapse", "gphoto_timelapse.*"]),
    entry_points={
        "console_scripts": [
            "camera-timelapse=gphoto_timelapse.cli:main",
        ],
    },
)
