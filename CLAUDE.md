# iriscc

Hydrological modelling workflows and Jupyter notebooks built around HydroMT, covering SFINCS (coastal flooding), FIAT (flood impact assessment), and D-HYDRO. Each model has a Solara-based interactive widget notebook under its `solara/` subfolder.

## Environment

This project uses [Pixi](https://pixi.sh) for dependency management. The `pyproject.toml` defines loose constraints; `pixi.lock` pins exact versions. Do not edit `pixi.lock` manually.

The `.yml` files under model subfolders (e.g. `SFINCS/solara/IRISCC_env.yml`) are legacy conda exports and are not used by Pixi.

### Install Pixi

Linux / macOS:
```bash
curl -fsSL https://pixi.sh/install.sh | bash
```

Windows (PowerShell):
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://pixi.sh/install.ps1 | iex"
```

Restart your shell after installation.

### Install the project environment

```bash
pixi install
```

## Running notebooks

Run all notebooks (executes in-place and saves outputs):
```bash
pixi run all-notebooks
```

Run a single notebook:
```bash
pixi run run-notebook <path/to/notebook.ipynb>
```

Strip outputs from all notebooks (for clean version control):
```bash
pixi run clean-notebooks
```

## Dev tasks

```bash
pixi run install-precommit   # install pre-commit hooks
pixi run lint                # run pre-commit on all files
```
