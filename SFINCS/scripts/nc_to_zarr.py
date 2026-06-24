#!/usr/bin/env python
"""Convert a NetCDF dataset to a Zarr store (local or S3), outside Jupyter.

Examples
--------
# S3 -> S3 (uses env vars or --key/--secret/--endpoint)
pixi run python SFINCS/scripts/nc_to_zarr.py \
    --src  s3://iriscc/topography/merit/merit.nc \
    --dst  s3://iriscc/topography/merit/merit.zarr \
    --drop-variables projection --chunks lat=6000 lon=6000

# Local -> local
pixi run python SFINCS/scripts/nc_to_zarr.py --src merit.nc --dst merit.zarr
"""

from __future__ import annotations

import argparse
import os

import xarray as xr


def _parse_chunks(items: list[str] | None) -> dict[str, int] | None:
    if not items:
        return None
    out: dict[str, int] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--chunks expects DIM=SIZE, got: {item!r}")
        dim, size = item.split("=", 1)
        out[dim.strip()] = int(size)
    return out


def _make_store(uri: str, *, write: bool, fs_kwargs: dict):
    """Return an object xarray can open/write.

    Local paths pass straight through; ``s3://`` paths are wrapped in an fsspec
    mapper/handle so no GDAL or netCDF4 S3 support is required.
    """
    if uri.startswith("s3://"):
        import s3fs

        fs = s3fs.S3FileSystem(**fs_kwargs)
        path = uri[len("s3://") :]
        if write:
            return s3fs.S3Map(path, s3=fs, create=True)
        # reading: open a file-like handle (works with the h5netcdf backend)
        return fs.open(uri)
    return uri  # local path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Convert NetCDF to Zarr (CLI, no Jupyter).")
    p.add_argument("--src", required=True, help="Source .nc URI (local path or s3://...)")
    p.add_argument("--dst", required=True, help="Destination .zarr URI (local path or s3://...)")
    p.add_argument(
        "--drop-variables",
        nargs="*",
        default=None,
        help="Variables to drop on read, e.g. projection",
    )
    p.add_argument(
        "--chunks",
        nargs="*",
        default=None,
        help="Rechunk before writing, e.g. lat=6000 lon=6000",
    )
    p.add_argument(
        "--engine",
        default="h5netcdf",
        help="xarray engine for reading NetCDF (default: h5netcdf)",
    )
    p.add_argument(
        "--zarr-format",
        type=int,
        default=2,
        choices=(2, 3),
        help="Zarr format version to write (default: 2)",
    )
    # S3 credentials (fall back to env vars if omitted)
    p.add_argument(
        "--endpoint",
        default=os.environ.get("AWS_S3_ENDPOINT_URL") or os.environ.get("AWS_S3_ENDPOINT"),
    )
    p.add_argument("--key", default=os.environ.get("AWS_ACCESS_KEY_ID"))
    p.add_argument("--secret", default=os.environ.get("AWS_SECRET_ACCESS_KEY"))
    p.add_argument(
        "--anon",
        action="store_true",
        help="Anonymous S3 access (public buckets)",
    )
    args = p.parse_args(argv)

    fs_kwargs: dict = {}
    if args.anon:
        fs_kwargs["anon"] = True
    else:
        if args.key:
            fs_kwargs["key"] = args.key
        if args.secret:
            fs_kwargs["secret"] = args.secret
    if args.endpoint:
        ep = args.endpoint if args.endpoint.startswith("http") else f"https://{args.endpoint}"
        fs_kwargs["client_kwargs"] = {"endpoint_url": ep}

    print(f"[nc_to_zarr] reading  {args.src}  (engine={args.engine})", flush=True)
    src_store = _make_store(args.src, write=False, fs_kwargs=fs_kwargs)
    ds = xr.open_dataset(
        src_store,
        engine=args.engine,
        drop_variables=args.drop_variables,
    )
    
    chunks = _parse_chunks(args.chunks)

    print(f"[nc_to_zarr] reading  {args.src}  (engine={args.engine}, chunks={chunks})", flush=True)
    src_store = _make_store(args.src, write=False, fs_kwargs=fs_kwargs)
    ds = xr.open_dataset(
        src_store,
        engine=args.engine,
        drop_variables=args.drop_variables,
        chunks=chunks or {},          # <-- dask-backed lazy read; {} = single chunk per var but still lazy
    )
    # Drop stale per-variable chunk encoding so to_zarr uses the dask chunks
    for v in ds.variables:
        ds[v].encoding.pop("chunks", None)
    
    #chunks = _parse_chunks(args.chunks)
    #if chunks:
    #    print(f"[nc_to_zarr] rechunking -> {chunks}", flush=True)
    #    ds = ds.chunk(chunks)
    #    # Zarr requires consistent chunk encoding; clear inherited per-var chunks.
    #    for v in ds.variables:
    #        ds[v].encoding.pop("chunks", None)

    print(f"[nc_to_zarr] writing  {args.dst}  (zarr_format={args.zarr_format})", flush=True)
    dst_store = _make_store(args.dst, write=True, fs_kwargs=fs_kwargs)
    ds.to_zarr(dst_store, mode="w", zarr_format=args.zarr_format, consolidated=True)

    ds.close()
    print("[nc_to_zarr] done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
