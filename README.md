# ProSpecPy

<span><img src="https://img.shields.io/badge/SSEC-Project-purple?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAA0AAAAOCAQAAABedl5ZAAAACXBIWXMAAAHKAAABygHMtnUxAAAAGXRFWHRTb2Z0d2FyZQB3d3cuaW5rc2NhcGUub3Jnm+48GgAAAMNJREFUGBltwcEqwwEcAOAfc1F2sNsOTqSlNUopSv5jW1YzHHYY/6YtLa1Jy4mbl3Bz8QIeyKM4fMaUxr4vZnEpjWnmLMSYCysxTcddhF25+EvJia5hhCudULAePyRalvUteXIfBgYxJufRuaKuprKsbDjVUrUj40FNQ11PTzEmrCmrevPhRcVQai8m1PRVvOPZgX2JttWYsGhD3atbHWcyUqX4oqDtJkJiJHUYv+R1JbaNHJmP/+Q1HLu2GbNoSm3Ft0+Y1YMdPSTSwQAAAABJRU5ErkJggg==&style=plastic" /><span>
[![DOI](https://zenodo.org/badge/836894886.svg)](https://zenodo.org/badge/latestdoi/836894886)
![BSD License](https://badgen.net/badge/license/BSD-3-Clause/blue)
[![Hatch project](https://img.shields.io/badge/%F0%9F%A5%9A-Hatch-4051b5.svg)](https://github.com/pypa/hatch)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

## Overview

ProSpecPy is a fully modular Python package developed to process FTIR
spectroscopy data from Bruker instruments. Created in collaboration between SSEC
and Dr. Elizabeth Phillips of The Grantham Institute at Imperial College London
(formerly Vincent Research Group at Oxford University), this tool streamlines
data analysis workflows and significantly reduces sample processing time.

The package is designed to be user-friendly and flexible, allowing researchers
to customize their data analysis workflows according to their specific needs.
ProSpecPy is built on the principles of modularity, interactivity, and
automation, making it a powerful tool for FTIR data processing.

ProSpecPy is designed to be used in conjunction with Jupyter Notebooks,
providing an interactive environment for data analysis. The package also
supports batch processing, allowing users to apply common operations across
multiple samples efficiently.

## Software Solution

ProSpecPy provides a comprehensive solution for FTIR data processing, addressing
the limitations of existing software tools. It is designed to be user-friendly
and flexible, allowing researchers to customize their data analysis workflows
according to their specific needs. The package is built on the following key
elements:

- A modular Python package for efficient FTIR data processing
- Jupyter Notebook integration for interactive data analysis
- Automated batch processing for common operations across samples
- User-customizable preferences for individual sample processing
- GitHub Codespaces integration for streamlined development

## Installation and Usage

For the easiest way to get started with ProSpecPy, we recommend using GitHub
Codespaces. This allows you to run the package in a cloud-based environment
without needing to install anything locally.

Click the button below 👇

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/uw-ssec/ProSpecPy?quickstart=1)

After the codespace is loaded up, begin by creating two folders within the main
directory: `data` and `notebooks`. Once you have created the `notebooks` folder,
make a copy of the
[workflow demo notebook](https://github.com/ProSpecPy/ProSpecPy/blob/main/docs/workflow_demo.ipynb)
from the doc folder and move it over. Once you have done so, change the name to
reflect the name of your run or experiment.

## Contributing

ProSpecPy is currently under development after an initial release. If you are
interested in contributing, please check out our open
[issues](https://github.com/ProSpecPy/ProSpecPy/issues) and fork the repository
to begin making changes within our object-oriented architecture.

## License

This project is licensed under the BSD 3-Clause License - see the
[LICENSE](./LICENSE) file for details.
