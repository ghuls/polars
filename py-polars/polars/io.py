from contextlib import contextmanager
from io import BytesIO, StringIO
from pathlib import Path
from typing import (
    Any,
    BinaryIO,
    Callable,
    ContextManager,
    Dict,
    Iterator,
    List,
    Optional,
    TextIO,
    Tuple,
    Type,
    Union,
    overload,
)
from urllib.request import urlopen

try:
    import pyarrow as pa
    import pyarrow.csv
    import pyarrow.feather
    import pyarrow.parquet

    _PYARROW_AVAILABLE = True
except ImportError:  # pragma: no cover
    _PYARROW_AVAILABLE = False

from polars.convert import from_arrow
from polars.datatypes import DataType
from polars.internals import DataFrame, LazyFrame

try:
    from polars.polars import ipc_schema as _ipc_schema
except ImportError:  # pragma: no cover
    pass

try:
    import connectorx as cx

    _WITH_CX = True
except ImportError:
    _WITH_CX = False

try:
    import fsspec
    from fsspec.utils import infer_storage_options

    _WITH_FSSPEC = True
except ImportError:
    _WITH_FSSPEC = False


def _process_http_file(path: str) -> BytesIO:
    with urlopen(path) as f:
        return BytesIO(f.read())


@overload
def _prepare_file_arg(
    file: Union[str, List[str], Path, BinaryIO, bytes], **kwargs: Any
) -> ContextManager[Union[str, BinaryIO]]:
    ...


@overload
def _prepare_file_arg(
    file: Union[str, TextIO, Path, BinaryIO, bytes], **kwargs: Any
) -> ContextManager[Union[str, BinaryIO]]:
    ...


@overload
def _prepare_file_arg(
    file: Union[str, List[str], TextIO, Path, BinaryIO, bytes], **kwargs: Any
) -> ContextManager[Union[str, List[str], BinaryIO, List[BinaryIO]]]:
    ...


def _prepare_file_arg(
    file: Union[str, List[str], TextIO, Path, BinaryIO, bytes], **kwargs: Any
) -> ContextManager[Union[str, BinaryIO, List[str], List[BinaryIO]]]:
    """
    Utility for read_[csv, parquet]. (not to be used by scan_[csv, parquet]).
    Returned value is always usable as a context.

    A `StringIO`, `BytesIO` file is returned as a `BytesIO`
    A local path is returned as a string
    An http url is read into a buffer and returned as a `BytesIO`

    When fsspec is installed, remote file(s) is (are) opened with
    `fsspec.open(file, **kwargs)` or `fsspec.open_files(file, **kwargs)`.
    """

    # Small helper to use a variable as context
    @contextmanager
    def managed_file(file: Any) -> Iterator[Any]:
        try:
            yield file
        finally:
            pass

    if isinstance(file, StringIO):
        return BytesIO(file.read().encode("utf8"))
    if isinstance(file, BytesIO):
        return file
    if isinstance(file, Path):
        return managed_file(str(file))
    if isinstance(file, str):
        if _WITH_FSSPEC:
            if infer_storage_options(file)["protocol"] == "file":
                return managed_file(file)
            return fsspec.open(file, **kwargs)
        if file.startswith("http"):
            return _process_http_file(file)
    if isinstance(file, list) and bool(file) and all(isinstance(f, str) for f in file):
        if _WITH_FSSPEC:
            if all(infer_storage_options(f)["protocol"] == "file" for f in file):
                return managed_file(file)
            return fsspec.open_files(file, **kwargs)
    return managed_file(file)


def update_columns(df: DataFrame, new_columns: List[str]) -> DataFrame:
    if df.width > len(new_columns):
        cols = df.columns
        for i, name in enumerate(new_columns):
            cols[i] = name
        new_columns = cols
    df.columns = new_columns
    return df


def read_csv(
    file: Union[str, TextIO, BytesIO, Path, BinaryIO, bytes],
    infer_schema_length: Optional[int] = 100,
    batch_size: int = 8192,
    has_header: bool = True,
    ignore_errors: bool = False,
    n_rows: Optional[int] = None,
    skip_rows: int = 0,
    projection: Optional[List[int]] = None,
    sep: str = ",",
    columns: Optional[List[str]] = None,
    rechunk: bool = True,
    encoding: str = "utf8",
    n_threads: Optional[int] = None,
    dtypes: Optional[Union[Dict[str, Type[DataType]], List[Type[DataType]]]] = None,
    new_columns: Optional[List[str]] = None,
    use_pyarrow: bool = False,
    low_memory: bool = False,
    comment_char: Optional[str] = None,
    quote_char: Optional[str] = r'"',
    storage_options: Optional[Dict] = None,
    null_values: Optional[Union[str, List[str], Dict[str, str]]] = None,
    parse_dates: bool = False,
    **kwargs: Any,
) -> DataFrame:
    """
    Read into a DataFrame from a csv file.

    Parameters
    ----------
    file
        Path to a file or a file like object.
        By file-like object, we refer to objects with a ``read()`` method,
        such as a file handler (e.g. via builtin ``open`` function)
        or ``StringIO`` or ``BytesIO``.
        If ``fsspec`` is installed, it will be used to open remote files
    infer_schema_length
        Maximum number of lines to read to infer schema. If set to 0, all columns will be read as pl.Utf8.
        If set to `None`, a full table scan will be done (slow).
    batch_size
        Number of lines to read into the buffer at once. Modify this to change performance.
    has_header
        Indicate if first row of dataset is header or not. If set to False first row will be set to `column_x`,
        `x` being an enumeration over every column in the dataset starting at 1.
    ignore_errors
        Try to keep reading lines if some lines yield errors.
    n_rows
        Stop reading from CSV file after reading ``n_rows``.
        During multi-threaded parsing, an upper bound of `n` rows
        cannot be guaranteed.
    skip_rows
        Start reading after `skip_rows`.
    projection
        Indices of columns to select. Note that column indices start at zero.
    sep
        Delimiter/ value separator.
    columns
        Columns to select.
    rechunk
        Make sure that all columns are contiguous in memory by aggregating the chunks into a single array.
    encoding
        - "utf8"
        - "utf8-lossy"
    n_threads
        Number of threads to use in csv parsing. Defaults to the number of physical cpu's of your system.
    dtypes
        Overwrite the dtypes during inference.
    new_columns
        Rename columns to these right after parsing. If the given list is shorted than the width of the DataFrame the
        remaining columns will have their original name.
    use_pyarrow
        Try to use pyarrow's native CSV parser. This is not always possible. The set of arguments given to this function
        determine if it is possible to use pyarrows native parser. Note that pyarrow and polars may have a different
        strategy regarding type inference.
    low_memory
        Reduce memory usage in expense of performance.
    comment_char
        character that indicates the start of a comment line, for instance '#'.
    quote_char
        single byte character that is used for csv quoting, default = ''. Set to None to turn special handling and escaping
        of quotes off.
    storage_options
        Extra options that make sense for ``fsspec.open()`` or a particular storage connection, e.g. host, port, username, password, etc.
    null_values
        Values to interpret as null values. You can provide a:

        - str -> all values encountered equal to this string will be null
        - List[str] -> A null value per column.
        - Dict[str, str] -> A dictionary that maps column name to a null value string.
    parse_dates
        Try to automatically parse dates. If this not succeeds, the column remains
        of data type Utf8.

    Returns
    -------
    DataFrame
    """
    # for backward compatibility
    dtypes = kwargs.get("dtypes", dtypes)

    if isinstance(file, bytes) and len(file) == 0:
        raise ValueError("no date in bytes")

    storage_options = storage_options or {}

    if columns and not has_header:
        for column in columns:
            if not column.startswith("column_"):
                raise ValueError(
                    'Specified column names do not start with "column_", '
                    "but autogenerated header names were requested."
                )

    if use_pyarrow and not _PYARROW_AVAILABLE:
        raise ImportError(
            "'pyarrow' is required when using 'read_csv(..., use_pyarrow=True)'."
        )

    if (
        use_pyarrow
        and dtypes is None
        and n_rows is None
        and n_threads is None
        and encoding == "utf8"
        and not low_memory
        and null_values is None
        and parse_dates
    ):
        include_columns = None

        if columns:
            if not has_header:
                # Convert 'column_1', 'column_2', ... column names to 'f0', 'f1', ... column names for pyarrow,
                # if CSV file does not contain a header.
                include_columns = [f"f{int(column[7:]) - 1}" for column in columns]
            else:
                include_columns = columns

        if not columns and projection:
            # Convert column indices from projection to 'f0', 'f1', ... column names for pyarrow.
            include_columns = [f"f{column_idx}" for column_idx in projection]

        with _prepare_file_arg(file, **storage_options) as data:
            tbl = pa.csv.read_csv(
                data,
                pa.csv.ReadOptions(
                    skip_rows=skip_rows, autogenerate_column_names=not has_header
                ),
                pa.csv.ParseOptions(delimiter=sep),
                pa.csv.ConvertOptions(
                    column_types=None,
                    include_columns=include_columns,
                    include_missing_columns=ignore_errors,
                ),
            )

        if not has_header:
            # Rename 'f0', 'f1', ... columns names autogenated by pyarrow to 'column_1', 'column_2', ...
            tbl = tbl.rename_columns(
                [f"column_{int(column[1:]) + 1}" for column in tbl.column_names]
            )

        df = from_arrow(tbl, rechunk)
        if new_columns:
            return update_columns(df, new_columns)  # type: ignore
        return df  # type: ignore

    if new_columns and dtypes and isinstance(dtypes, dict):
        current_columns = None

        # As new column names are not available yet while parsing the CSV file, rename column names in
        # dtypes to old names (if possible) so they can be used during CSV parsing.
        if columns:
            if len(columns) < len(new_columns):
                raise ValueError(
                    "More new colum names are specified than there are selected columns."
                )

            # Get column names of requested columns.
            current_columns = columns[0 : len(new_columns)]
        elif not has_header:
            # When there are no header, column names are autogenerated (and known).

            if projection:
                if columns and len(columns) < len(new_columns):
                    raise ValueError(
                        "More new colum names are specified than there are projected columns."
                    )
                # Convert column indices from projection to 'column_1', 'column_2', ... column names.
                current_columns = [
                    f"column_{column_idx + 1}" for column_idx in projection
                ]
            else:
                # Generate autogenerated 'column_1', 'column_2', ... column names for new column names.
                current_columns = [
                    f"column_{column_idx}"
                    for column_idx in range(1, len(new_columns) + 1)
                ]
        else:
            # When a header is present, column names are not known yet.

            if len(dtypes) <= len(new_columns):
                # If dtypes dictionary contains less or same amount of values than new column names
                # a list of dtypes can be created if all listed column names in dtypes dictionary
                # appear in the first consecutive new column names.
                dtype_list = [
                    dtypes[new_column_name]
                    for new_column_name in new_columns[0 : len(dtypes)]
                    if new_column_name in dtypes
                ]

                if len(dtype_list) == len(dtypes):
                    dtypes = dtype_list

        if current_columns and isinstance(dtypes, dict):
            new_to_current = {
                new_column: current_column
                for new_column, current_column in zip(new_columns, current_columns)
            }
            # Change new column names to current column names in dtype.
            dtypes = {
                new_to_current.get(column_name, column_name): column_dtype
                for column_name, column_dtype in dtypes.items()
            }

    with _prepare_file_arg(file, **storage_options) as data:
        df = DataFrame.read_csv(
            file=data,
            infer_schema_length=infer_schema_length,
            batch_size=batch_size,
            has_header=has_header,
            ignore_errors=ignore_errors,
            n_rows=n_rows,
            skip_rows=skip_rows,
            projection=projection,
            sep=sep,
            columns=columns,
            rechunk=rechunk,
            encoding=encoding,
            n_threads=n_threads,
            dtypes=dtypes,
            low_memory=low_memory,
            comment_char=comment_char,
            quote_char=quote_char,
            null_values=null_values,
            parse_dates=parse_dates,
        )

    if new_columns:
        return update_columns(df, new_columns)
    return df


def scan_csv(
    file: Union[str, Path],
    infer_schema_length: Optional[int] = 100,
    has_header: bool = True,
    ignore_errors: bool = False,
    sep: str = ",",
    skip_rows: int = 0,
    n_rows: Optional[int] = None,
    cache: bool = True,
    dtype: Optional[Dict[str, Type[DataType]]] = None,
    low_memory: bool = False,
    comment_char: Optional[str] = None,
    quote_char: Optional[str] = r'"',
    null_values: Optional[Union[str, List[str], Dict[str, str]]] = None,
    with_column_names: Optional[Callable[[List[str]], List[str]]] = None,
) -> LazyFrame:
    """
    Lazily read from a csv file.

    This allows the query optimizer to push down predicates and projections to the scan level,
    thereby potentially reducing memory overhead.

    Parameters
    ----------
    file
        Path to a file.
    infer_schema_length
        The number of rows Polars will read to try to determine the schema.
    has_header
        If the CSV file has headers or not.
    ignore_errors
        Try to keep reading lines if some lines yield errors.
    sep
        Delimiter/ value separator.
    skip_rows
        Start reading after `skip_rows`.
    n_rows
        Stop reading from IPC file after reading ``n_rows``.
        During multi-threaded parsing, an upper bound of `n` rows cannot be guaranteed.
    cache
        Cache the result after reading.
    dtype
        Overwrite the dtypes during inference.
    low_memory
        Reduce memory usage in expense of performance.
    comment_char
        character that indicates the start of a comment line, for instance '#'.
    quote_char
        single byte character that is used for csv quoting, default = ''. Set to None to turn special handling and escaping
        of quotes off.
    null_values
        Values to interpret as null values. You can provide a:

        - str -> all values encountered equal to this string will be null
        - List[str] -> A null value per column.
        - Dict[str, str] -> A dictionary that maps column name to a null value string.
    with_column_names
        Apply a function over the column names. This can be used to update a schema just in time, thus before scanning.


    Examples
    --------
    >>> (
    ...     pl.scan_csv("my_long_file.csv")  # lazy, doesn't do a thing
    ...     .select(
    ...         ["a", "c"]
    ...     )  # select only 2 columns (other columns will not be read)
    ...     .filter(
    ...         pl.col("a") > 10
    ...     )  # the filter is pushed down the the scan, so less data read in memory
    ...     .fetch(100)  # pushed a limit of 100 rows to the scan level
    ... )  # doctest: +SKIP

    We can use `with_column_names` to modify the header before scanning:

    >>> df = pl.DataFrame(
    ...     {"BrEeZaH": [1, 2, 3, 4], "LaNgUaGe": ["is", "terrible", "to", "read"]}
    ... )
    >>> df.to_csv("mydf.csv")
    >>> pl.scan_csv(
    ...     "mydf.csv", with_column_names=lambda cols: [col.lower() for col in cols]
    ... ).fetch()
    shape: (4, 2)
    ┌─────────┬──────────┐
    │ breezah ┆ language │
    │ ---     ┆ ---      │
    │ i64     ┆ str      │
    ╞═════════╪══════════╡
    │ 1       ┆ is       │
    ├╌╌╌╌╌╌╌╌╌┼╌╌╌╌╌╌╌╌╌╌┤
    │ 2       ┆ terrible │
    ├╌╌╌╌╌╌╌╌╌┼╌╌╌╌╌╌╌╌╌╌┤
    │ 3       ┆ to       │
    ├╌╌╌╌╌╌╌╌╌┼╌╌╌╌╌╌╌╌╌╌┤
    │ 4       ┆ read     │
    └─────────┴──────────┘


    """
    if isinstance(file, Path):
        file = str(file)
    return LazyFrame.scan_csv(
        file=file,
        has_header=has_header,
        sep=sep,
        ignore_errors=ignore_errors,
        skip_rows=skip_rows,
        n_rows=n_rows,
        cache=cache,
        dtype=dtype,
        low_memory=low_memory,
        comment_char=comment_char,
        quote_char=quote_char,
        null_values=null_values,
        infer_schema_length=infer_schema_length,
        with_column_names=with_column_names,
    )


def scan_ipc(
    file: Union[str, Path],
    n_rows: Optional[int] = None,
    cache: bool = True,
) -> LazyFrame:
    """
    Lazily read from an Arrow IPC (Feather v2) file.

    This allows the query optimizer to push down predicates and projections to the scan level,
    thereby potentially reducing memory overhead.

    Parameters
    ----------
    file
        Path to a IPC file.
    n_rows
        Stop reading from IPC file after reading ``n_rows``.
    cache
        Cache the result after reading.
    """
    if isinstance(file, Path):
        file = str(file)
    return LazyFrame.scan_ipc(
        file=file, n_rows=n_rows, cache=cache
    )


def scan_parquet(
    file: Union[str, Path],
    n_rows: Optional[int] = None,
    cache: bool = True,
) -> LazyFrame:
    """
    Lazily read from a parquet file.

    This allows the query optimizer to push down predicates and projections to the scan level,
    thereby potentially reducing memory overhead.

    Parameters
    ----------
    file
        Path to a file.
    n_rows
        Stop reading from parquet file after reading ``n_rows``.
    cache
        Cache the result after reading.
    """
    if isinstance(file, Path):
        file = str(file)
    return LazyFrame.scan_parquet(
        file=file, n_rows=n_rows, cache=cache
    )


def read_ipc_schema(
    file: Union[str, BinaryIO, Path, bytes]
) -> Dict[str, Type[DataType]]:
    """
    Get a schema of the IPC file without reading data.

    Parameters
    ----------
    file
        Path to a file or a file like object.

    Returns
    -------
    Dictionary mapping column names to datatypes
    """
    return _ipc_schema(file)


def read_ipc(
    file: Union[str, BinaryIO, BytesIO, Path, bytes],
    columns: Optional[Union[List[int], List[str]]] = None,
    projection: Optional[List[int]] = None,
    n_rows: Optional[int] = None,
    use_pyarrow: bool = _PYARROW_AVAILABLE,
    memory_map: bool = True,
    storage_options: Optional[Dict] = None,
) -> DataFrame:
    """
    Read into a DataFrame from Arrow IPC (Feather v2) file.

    Parameters
    ----------
    file
        Path to a file or a file like object.
        If ``fsspec`` is installed, it will be used to open remote files.
    columns
        Columns to select. Accepts a list of column indices (starting at zero) or a list of column names.
    n_rows
        Stop reading from IPC file after reading ``n_rows``.
        Only valid when `use_pyarrow=False`.
    use_pyarrow
        Use pyarrow or the native rust reader.
    memory_map
        Memory map underlying file. This will likely increase performance.
        Only used when ``use_pyarrow=True``.
    storage_options
        Extra options that make sense for ``fsspec.open()`` or a particular storage connection, e.g. host, port, username, password, etc.

    Returns
    -------
    DataFrame
    """
    if use_pyarrow:
        if n_rows:
            raise ValueError(
                "``n_rows`` cannot be used with ``use_pyarrow=True``."
            )

    storage_options = storage_options or {}
    with _prepare_file_arg(file, **storage_options) as data:
        if use_pyarrow:
            if not _PYARROW_AVAILABLE:
                raise ImportError(
                    "'pyarrow' is required when using 'read_ipc(..., use_pyarrow=True)'."
                )

            # pyarrow accepts column names or column indices.
            tbl = pa.feather.read_table(
                data, memory_map=memory_map, columns=columns if columns else projection
            )
            return DataFrame._from_arrow(tbl)

        if columns:
            # Unset projection if column names where specified.
            projection = None

        return DataFrame.read_ipc(
            data,
            columns=columns,
            projection=projection,
            n_rows=n_rows,
        )


def read_parquet(
    source: Union[str, List[str], Path, BinaryIO, BytesIO, bytes],
    columns: Optional[Union[List[int], List[str]]] = None,
    projection: Optional[List[int]] = None,
    n_rows: Optional[int] = None,
    use_pyarrow: bool = _PYARROW_AVAILABLE,
    memory_map: bool = True,
    storage_options: Optional[Dict] = None,
    **kwargs: Any,
) -> DataFrame:
    """
    Read into a DataFrame from a parquet file.

    Parameters
    ----------
    source
        Path to a file, list of files, or a file like object. If the path is a directory, that directory will be used
        as partition aware scan.
        If ``fsspec`` is installed, it will be used to open remote files.
    columns
        Columns to select. Accepts a list of column indices (starting at zero) or a list of column names.
    projection
        Indices of columns to select. Note that column indices start at zero.
    n_rows
        Stop reading from parquet file after reading ``n_rows``.
        Only valid when `use_pyarrow=False`.
    use_pyarrow
        Use pyarrow instead of the rust native parquet reader. The pyarrow reader is more stable.
    memory_map
        Memory map underlying file. This will likely increase performance.
        Only used when ``use_pyarrow=True``.
    storage_options
        Extra options that make sense for ``fsspec.open()`` or a particular storage connection, e.g. host, port, username, password, etc.
    **kwargs
        kwargs for [pyarrow.parquet.read_table](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.read_table.html)

    Returns
    -------
    DataFrame
    """
    if use_pyarrow:
        if n_rows:
            raise ValueError(
                "``n_rows`` cannot be used with ``use_pyarrow=True``."
            )

    storage_options = storage_options or {}
    with _prepare_file_arg(source, **storage_options) as source_prep:
        if use_pyarrow:
            if not _PYARROW_AVAILABLE:
                raise ImportError(
                    "'pyarrow' is required when using 'read_parquet(..., use_pyarrow=True)'."
                )

            # pyarrow accepts column names or column indices.
            return from_arrow(  # type: ignore[return-value]
                pa.parquet.read_table(
                    source_prep,
                    memory_map=memory_map,
                    columns=columns if columns else projection,
                    **kwargs,
                )
            )

        if columns:
            # Unset projection if column names where specified.
            projection = None

        return DataFrame.read_parquet(
            source_prep,
            columns=columns,
            projection=projection,
            n_rows=n_rows,
        )


def read_json(source: Union[str, BytesIO]) -> DataFrame:
    """
    Read into a DataFrame from JSON format.

    Parameters
    ----------
    source
        Path to a file or a file like object.
    """
    return DataFrame.read_json(source)


def read_sql(
    sql: Union[List[str], str],
    connection_uri: str,
    partition_on: Optional[str] = None,
    partition_range: Optional[Tuple[int, int]] = None,
    partition_num: Optional[int] = None,
    protocol: Optional[str] = None,
) -> DataFrame:
    """
    Read a SQL query into a DataFrame.
    Make sure to install connectorx>=0.2

    # Sources
    Supports reading a sql query from the following data sources:

    * Postgres
    * Mysql
    * Sqlite
    * Redshift (through postgres protocol)
    * Clickhouse (through mysql protocol)

    ## Source not supported?
    If a database source is not supported, pandas can be used to load the query:

    >>> import pandas as pd
    >>> df = pl.from_pandas(pd.read_sql(sql, engine))  # doctest: +SKIP

    Parameters
    ----------
    sql
        raw sql query.
    connection_uri
        connectorx connection uri:
            - "postgresql://username:password@server:port/database"
    partition_on
      the column on which to partition the result.
    partition_range
      the value range of the partition column.
    partition_num
      how many partitions to generate.
    protocol
      backend-specific transfer protocol directive; see connectorx documentation for details.

    Examples
    --------

    ## Single threaded
    Read a DataFrame from a SQL query using a single thread:

    >>> uri = "postgresql://username:password@server:port/database"
    >>> query = "SELECT * FROM lineitem"
    >>> pl.read_sql(query, uri)  # doctest: +SKIP

    ## Using 10 threads
    Read a DataFrame in parallel using 10 threads by automatically partitioning the provided SQL on the partition column:

    >>> uri = "postgresql://username:password@server:port/database"
    >>> query = "SELECT * FROM lineitem"
    >>> pl.read_sql(
    ...     query, uri, partition_on="partition_col", partition_num=10
    ... )  # doctest: +SKIP

    ## Using
    Read a DataFrame in parallel using 2 threads by explicitly providing two SQL queries:

    >>> uri = "postgresql://username:password@server:port/database"
    >>> queries = [
    ...     "SELECT * FROM lineitem WHERE partition_col <= 10",
    ...     "SELECT * FROM lineitem WHERE partition_col > 10",
    ... ]
    >>> pl.read_sql(uri, queries)  # doctest: +SKIP

    """
    if _WITH_CX:
        tbl = cx.read_sql(
            conn=connection_uri,
            query=sql,
            return_type="arrow",
            partition_on=partition_on,
            partition_range=partition_range,
            partition_num=partition_num,
            protocol=protocol,
        )
        return from_arrow(tbl)  # type: ignore[return-value]
    else:
        raise ImportError(
            "connectorx is not installed." "Please run pip install connectorx>=0.2.2"
        )
