#!/usr/bin/env python3

"""
In-Memory Mongo-Flavored Queries.

jque is a Python module that lets you query in-memory lists of dicts as though
they were in a Mongo database.
"""
from typing import List

import json
import copy
import types

try:
    from deco import synchronized, concurrent

    _DECO_SUPPORTED = True
except ImportError:
    concurrent = lambda x: x
    synchronized = lambda x: x
    _DECO_SUPPORTED = False

try:
    import pandas as pd

    _PANDAS_SUPPORTED = True
except ImportError:
    _PANDAS_SUPPORTED = False

__version__ = "0.2.0"


_OPERATORS = {
    "$eq": lambda x, y: x == y,
    "$neq": lambda x, y: x != y,
    "$lt": lambda x, y: x < y,
    "$lte": lambda x, y: x <= y,
    "$gt": lambda x, y: x > y,
    "$gte": lambda x, y: x >= y,
    "$in": lambda x, y: x in y,
    "$nin": lambda x, y: x not in y,
}


@concurrent
def _check_record_parallel(qr, record):
    return _check_record(qr, record)


def _check_record(qr, record):
    for key, qual in qr.items():
        if isinstance(qual, dict):
            for op, val in qual.items():
                if op not in _OPERATORS:
                    raise ValueError("'{}' is not a valid operator.".format(op))
                if not _OPERATORS[op](record[key], val):
                    return False
        elif isinstance(qual, types.FunctionType):
            if not qual(record[key]):
                return False
        else:
            if record[key] != qual:
                return False
    return True


class jque:
    """
    A JSON query class that subsets the behavior of MongoDB queries.

    Uses $-notation for mongo operators.

        data = jque.jsonque([{
            "_id": "ABC",
            "name": "Arthur Dent",
            "age": 42,
            "current_planet": "earth"
        }, {
            "_id": "DE2",
            "name": "Penny Lane",
            "age": 19,
            "current_planet": "earth"
        }, {
            "_id": "123",
            "name": "Ford Prefect",
            "age": 240,
            "current_planet": "Brontitall"
        }])

        teenage_earthlings = data.query({
            "current_planet": "earth",
            "age": { "$lte": 20, "$gte": 10 }
        })

    """

    OPERATORS = _OPERATORS

    def __init__(self, data, parallel=False):
        """
        Create a new jque object. Pass `data`, which must be a
        string or a list. If a list, each item should be a dictionary.
        If a string, it can either be a JSON string (from Python's
        json.dumps or JS's JSON.stringify) or a filename that points
        to a .json file on disk.
        """
        self.parallel = parallel
        self._is_pandas = False
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                data = json.loads(open(data, "r").read())
        elif _PANDAS_SUPPORTED and isinstance(data, pd.DataFrame):
            self._is_pandas = True
        elif not isinstance(data, list):
            raise ValueError(
                "'data' argument must be a string, pandas.DataFrame, or a list[dict]."
            )
        self.data = data

        self._iter_items = (
            lambda x: [v for _, v in x.iterrows()] if self._is_pandas else list
        )

    def __getitem__(self, key):
        return self.data[key]

    def __len__(self):
        return len(self.data)

    def query(self, qr, wrap=True, limit=None):
        """
        Query the records for a desired trait.

        Arguments:
            qr (dict): a dict where all keys are included in all records.
            wrap (bool : True): If the result should be rewrapped in a
                new jque object.

        Examples:

        >>> data = jque([{
        ...     "_id": "ABC",
        ...     "name": "Arthur Dent",
        ...     "age": 42,
        ...     "current_planet": "earth"
        ... }, {
        ...     "_id": "DE2",
        ...     "name": "Penny Lane",
        ...     "age": 19,
        ...     "current_planet": "earth"
        ... }, {
        ...     "_id": "123",
        ...     "name": "Ford Prefect",
        ...     "age": 240,
        ...     "current_planet": "Brontitall"
        ... }])
        >>> len(data.query({ current_planet: "earth" })) == 2
        True
        >>> len(data.query({ current_planet: "earth" }), limit=1) == 1
        True
        """

        if self.parallel:
            # TODO: Concurrent support for limits
            results = _parallel_query(qr, self.data)
            filtered_results = [d for d, r in zip(self.data, results) if r][:limit]
            if wrap:
                return jque(filtered_results)
            return filtered_results

        filtered_data = []
        for record in self._iter_items(self.data):
            include = _check_record(qr, record)
            if include:
                filtered_data.append(record)
                if limit and len(filtered_data) >= limit:
                    break
        if wrap:
            return jque(filtered_data)
        return filtered_data


@synchronized
def _parallel_query(qr, data) -> List[bool]:
    results = [False] * len(data)
    for i in range(len(data)):
        results[i] = _check_record(qr, data[i])
    return results
