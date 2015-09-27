#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: sw=4:ts=4:expandtab

"""
tabutils.process
~~~~~~~~~~~~~~~~

Provides methods for processing data from tabular formatted files

Examples:
    literal blocks::

        from tabutils.process import underscorify

        header = ['ALL CAPS', 'Illegal $%^', 'Lots of space']
        names = underscorify(header)

Attributes:
    CURRENCIES [tuple(unicode)]: Currency symbols to remove from decimal
        strings.
"""

from __future__ import (
    absolute_import, division, print_function, with_statement,
    unicode_literals)

import itertools as it
import hashlib

from os import path as p
from decimal import Decimal, InvalidOperation, ROUND_UP, ROUND_DOWN
from dateutil.parser import parse
from functools import partial

from slugify import slugify

CURRENCIES = ('$', '£', '€')

underscorify = lambda fields: [slugify(f, separator='_') for f in fields]


def make_float(value):
    """Parses and formats numbers into floats.

    Args:
        value (str): The number to parse.

    Returns:
        flt: The parsed number.

    Examples:
        >>> make_float('1')
        1.0
        >>> make_float('1f')
    """
    if value and value.strip():
        try:
            value = float(value.replace(',', ''))
        except ValueError:
            value = None
    else:
        value = None

    return value


def decimalize(value, **kwargs):
    """Parses and formats currency values into decimals
    >>> decimalize('$123.45')
    Decimal('123.45')
    >>> decimalize('123€')
    Decimal('123.00')
    >>> decimalize('2,123.45')
    Decimal('2123.45')
    >>> decimalize('2.123,45', thousand_sep='.', decimal_sep=',')
    Decimal('2123.45')
    >>> decimalize('spam')
    """
    thousand_sep = kwargs.get('thousand_sep', ',')
    decimal_sep = kwargs.get('decimal_sep', '.')
    places = kwargs.get('places', 2)
    roundup = kwargs.get('roundup', True)

    rounding = ROUND_UP if roundup else ROUND_DOWN
    precision = '.%s1' % ''.join(it.repeat('0', places - 1))

    currencies = it.izip(CURRENCIES, it.repeat(''))
    seperators = [(thousand_sep, ''), (decimal_sep, '.')]

    try:
        stripped = mreplace(value, it.chain(currencies, seperators))
    except AttributeError:
        # We don't have a string
        stripped = value

    try:
        decimalized = Decimal(stripped)
    except InvalidOperation:
        quantized = None
    else:
        quantized = decimalized.quantize(Decimal(precision), rounding=rounding)

    return quantized


def is_numeric_like(string, seperators=('.', ',')):
    """
    >>> is_numeric_like('$123.45')
    True
    >>> is_numeric_like('123€')
    True
    >>> is_numeric_like('2,123.45')
    True
    >>> is_numeric_like('2.123,45')
    True
    >>> is_numeric_like('10e5')
    True
    >>> is_numeric_like('spam')
    False
    """
    replacements = it.izip(it.chain(CURRENCIES, seperators), it.repeat(''))
    stripped = mreplace(string, replacements)

    try:
        float(stripped)
    except (ValueError, TypeError):
        return False
    else:
        return True


def afterish(string, char=',', exclude=None):
    """Number of digits after a given character.

    >>> afterish('123.45', '.')
    2
    >>> afterish('1001.', '.')
    0
    >>> afterish('1001', '.')
    -1
    >>> afterish('1,001')
    3
    >>> afterish('2,100,001.00')
    6
    >>> afterish('2,100,001.00', exclude='.')
    3
    >>> afterish('1,000.00', '.', ',')
    2
    >>> afterish('eggs', '.')
    Traceback (most recent call last):
    TypeError: Not able to convert eggs to a number
    """
    numeric_like = is_numeric_like(string)

    if numeric_like and char in string:
        excluded = [s for s in string.split(exclude) if char in s][0]
        after = len(excluded) - excluded.rfind(char) - 1
    elif numeric_like:
        after = -1
    else:
        raise TypeError('Not able to convert %s to a number' % string)

    return after


def mreplace(string, replacements):
    func = lambda x, y: x.replace(y[0], y[1])
    return reduce(func, replacements, string)


def xmlize(content):
    """ Recursively makes elements of an array xml compliant

    Args:
        content (List[str]): the content to clean

    Yields:
        (str): the cleaned element

    Examples:
        >>> list(xmlize(['&', '<']))
        [u'&amp', u'&lt']
    """
    replacements = [
        ('&', '&amp'), ('>', '&gt'), ('<', '&lt'), ('\n', ' '), ('\r\n', ' ')]

    for item in content:
        if hasattr(item, 'upper'):
            yield mreplace(item, replacements)
        else:
            try:
                yield list(xmlize(item))
            except TypeError:
                yield mreplace(item, replacements) if item else ''


def _make_date(value, date_format):
    """Parses and formats date strings.

    Args:
        value (str): The date to parse.
        date_format (str): Date format passed to `strftime()`.

    Returns:
        [tuple(str, bool)]: Tuple of the formatted date string and retry value.

    Examples:
        >>> _make_date('5/4/82', '%Y-%m-%d')
        ('1982-05-04', False)
        >>> _make_date('2/32/82', '%Y-%m-%d')
        (u'2/32/82', True)
    """
    try:
        if value and value.strip():
            value = parse(value).strftime(date_format)

        retry = False
    # impossible date, e.g., 2/31/15
    except ValueError:
        retry = True
    # unparseable date, e.g., Novmbr 4
    except TypeError:
        value = None
        retry = False

    return (value, retry)


def make_date(value, date_format):
    """Parses and formats date strings.

    Args:
        value (str): The date to parse.
        date_format (str): Date format passed to `strftime()`.

    Returns:
        str: The formatted date string.

    Examples:
        >>> make_date('5/4/82', '%Y-%m-%d')
        '1982-05-04'
        >>> make_date('2/32/82', '%Y-%m-%d')
        '1982-02-28'
    """
    value, retry = _make_date(value, date_format)

    # Fix impossible dates, e.g., 2/31/15
    if retry:
        bad_num = [x for x in ['29', '30', '31', '32'] if x in value][0]
        possibilities = [value.replace(bad_num, x) for x in ['30', '29', '28']]

        for possible in possibilities:
            value, retry = _make_date(possible, date_format)

            if retry:
                continue
            else:
                break

    return value


def gen_type_cast(records, fields, date_format='%Y-%m-%d'):
    """Casts record entries based on field types.

    Args:
        records (List[dicts]): Record entries (`read_csv` output).
        fields (List[dicts]): Field types (`gen_fields` output).
        date_format (str): Date format passed to `strftime()` (default:
            '%Y-%m-%d', i.e, 'YYYY-MM-DD').

    Yields:
        dict: The type casted record entry.

    Examples:
        >>> from . import io
        >>> parent_dir = p.abspath(p.dirname(p.dirname(__file__)))
        >>> csv_filepath = p.join(parent_dir, 'data', 'test', 'test.csv')
        >>> csv_records = io.read_csv(csv_filepath, sanitize=True)
        >>> csv_header = sorted(csv_records.next().keys())
        >>> csv_fields = gen_fields(csv_header, True)
        >>> csv_records.next()['some_date']
        u'05/04/82'
        >>> casted_csv_row = gen_type_cast(csv_records, csv_fields).next()
        >>> casted_csv_values = [casted_csv_row[h] for h in csv_header]
        >>>
        >>> xls_filepath = p.join(parent_dir, 'data', 'test', 'test.xls')
        >>> xls_records = io.read_xls(xls_filepath, sanitize=True)
        >>> xls_header = sorted(xls_records.next().keys())
        >>> xls_fields = gen_fields(xls_header, True)
        >>> xls_records.next()['some_date']
        '1982-05-04'
        >>> casted_xls_row = gen_type_cast(xls_records, xls_fields).next()
        >>> casted_xls_values = [casted_xls_row[h] for h in xls_header]
        >>>
        >>> casted_csv_values == casted_xls_values
        True
        >>> casted_csv_values
        ['2015-01-01', 100.0, None, None]
    """
    make_date_p = partial(make_date, date_format=date_format)
    make_unicode = lambda v: unicode(v) if v and v.strip() else None
    switch = {'float': make_float, 'date': make_date_p, 'text': make_unicode}
    field_types = {f['id']: f['type'] for f in fields}

    for row in records:
        yield {k: switch.get(field_types[k])(v) for k, v in row.items()}


def gen_fields(names, type_cast=False):
    """Tries to determine field types based on field names.

    Args:
        names (List[str]): Field names.

    Yields:
        dict: The parsed field with type

    Examples:
        >>> gen_fields(['date', 'raw_value', 'text']).next()
        {u'type': u'text', u'id': u'date'}
    """
    for name in names:
        if type_cast and 'date' in name:
            yield {'id': name, 'type': 'date'}
        elif type_cast and 'value' in name:
            yield {'id': name, 'type': 'float'}
        else:
            yield {'id': name, 'type': 'text'}


def hash_file(filepath, hasher='sha1', chunksize=0, verbose=False):
    """Hashes a file.
    http://stackoverflow.com/a/1131255/408556

    Args:
        filepath (str): The file path or file like object to write to.
        hasher (str): The hashlib hashing algorithm to use.
        chunksize (Optional[int]): Number of bytes to write at a time (default:
            0, i.e., all).
        verbose (Optional[bool]): Print debug statements (default: False).

    Returns:
        str: File hash.

    Examples:
        >>> from tempfile import TemporaryFile
        >>> hash_file(TemporaryFile())
        'da39a3ee5e6b4b0d3255bfef95601890afd80709'
    """
    def read_file(f, hasher):
        if chunksize:
            while True:
                data = f.read(chunksize)
                if not data:
                    break

                hasher.update(data)
        else:
            hasher.update(f.read())

        return hasher.hexdigest()

    hasher = getattr(hashlib, hasher)()

    if hasattr(filepath, 'read'):
        file_hash = read_file(filepath, hasher)
    else:
        with open(filepath, 'rb') as f:
            file_hash = read_file(f, hasher)

    if verbose:
        print('File %s hash is %s.' % (filepath, file_hash))

    return file_hash


def make_filepath(filepath, **kwargs):
    """Creates a filepath from an online resource, i.e., linked file or
    google sheets export.

    Args:
        filepath (str): Output file path or directory.
        **kwargs: Keyword arguments.

    Kwargs:
        headers (dict): HTTP response headers, e.g., `r.headers`.
        name_from_id (bool): Overwrite filename with resource id.
        resource_id (str): The resource id (required if `name_from_id` is True
            or filepath is a google sheets export)

    Returns:
        str: filepath

    Examples:
        >>> make_filepath('file.csv')
        u'file.csv'
        >>> make_filepath('.', resource_id='rid')
        Content-Type None not found in dictionary. Using default value.
        u'./rid.csv'
    """
    isdir = p.isdir(filepath)
    headers = kwargs.get('headers') or {}
    name_from_id = kwargs.get('name_from_id')
    resource_id = kwargs.get('resource_id')

    if isdir and not name_from_id:
        try:
            disposition = headers.get('content-disposition', '')
            filename = disposition.split('=')[1].split('"')[1]
        except (KeyError, IndexError):
            filename = resource_id
    elif isdir or name_from_id:
        filename = resource_id

    if isdir and filename.startswith('export?format='):
        filename = '%s.%s' % (resource_id, filename.split('=')[1])
    elif isdir and '.' not in filename:
        ctype = headers.get('content-type')
        filename = '%s.%s' % (filename, ctype2ext(ctype))

    return p.join(filepath, filename) if isdir else filepath


def ctype2ext(content_type=None):
    try:
        ctype = content_type.split('/')[1].split(';')[0]
    except (AttributeError, IndexError):
        ctype = None

    xlsx_type = 'vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    switch = {'xls': 'xls', 'csv': 'csv'}
    switch[xlsx_type] = 'xlsx'

    if ctype not in switch:
        print(
            'Content-Type %s not found in dictionary. Using default value.'
            % ctype)

    return switch.get(ctype, 'csv')


def to_bytearray(content):
    try:
        return bytearray(content)
    except ValueError:  # has unicode chars
        return reduce(lambda x, y: x + y, it.imap(bytearray, content))


def chunk(content, chunksize=None, start=0, stop=None):
    """Groups data into fixed-sized chunks.
    http://stackoverflow.com/a/22919323/408556

    Args:
        content (obj): File like object, iterable response, or iterable.
        chunksize (Optional[int]): Number of bytes per chunk (default: 0,
            i.e., all).

        start (Optional[int]): Starting location (zero indexed, default: 0).
        stop (Optional[int]): Ending location (zero indexed).

    Returns:
        Iter[List]: Chunked content.

    Examples:
        >>> import requests
        >>> from StringIO import StringIO
        >>> from . import io
        >>> chunk([1, 2, 3, 4, 5, 6]).next()
        [1, 2, 3, 4, 5, 6]
        >>> chunk([1, 2, 3, 4, 5, 6], 2).next()
        [1, 2]
        >>> chunk(StringIO('Hello World'), 5).next()
        u'Hello'
        >>> chunk(io.IterStringIO('Hello World'), 5).next()
        bytearray(b'Hello')
        >>> chunk(io.IterStringIO('Hello World')).next()
        bytearray(b'Hello World')
        >>> r = requests.get('http://google.com', stream=True)
        >>> len(chunk(r.iter_content, 20, 29, 200).next())
        20
        >>> len(chunk(r.iter_content).next()) > 10000
        True
    """
    if hasattr(content, 'read'):  # it's a file
        content.seek(start) if start else None
        content.truncate(stop) if stop else None

        if chunksize:
            generator = (content.read(chunksize) for _ in it.count())
        else:
            generator = iter([content.read()])
    elif callable(content):  # it's an r.iter_content
        chunksize = chunksize or pow(2, 34)

        if start or stop:
            i = it.islice(content(), start, stop)
            generator = (
                to_bytearray(it.islice(i, chunksize)) for _ in it.count())
        else:
            generator = content(chunksize)
    else:  # it's a regular iterable
        i = it.islice(iter(content), start, stop)

        if chunksize:
            generator = (list(it.islice(i, chunksize)) for _ in it.count())
        else:
            generator = iter([list(i)])

    return it.takewhile(bool, generator)


def _fuzzy_match(items, possibilities, **kwargs):
    for i in items:
        for p in possibilities:
            if p in i.lower():
                yield i


def _exact_match(*args, **kwargs):
    sets = (set(i.lower() for i in arg) for arg in args)
    return iter(reduce(lambda x, y: x.intersection(y), sets))


def find(*args, **kwargs):
    method = kwargs.pop('method', 'exact')
    default = kwargs.pop('default', '')
    funcs = {'exact': _exact_match, 'fuzzy': _fuzzy_match}
    func = funcs.get('method', method)

    try:
        return func(*args, **kwargs).next()
    except StopIteration:
        return default


def merge_dicts(*dicts, **kwargs):
    """Merges a list of dicts. Optionally combines specified keys using a
    specified binary operator.

    http://codereview.stackexchange.com/a/85822/71049
    http://stackoverflow.com/a/31812635/408556
    http://stackoverflow.com/a/3936548/408556

    Args:
        dicts Iter[dict]: dicts to merge
        kwargs (dict): keyword arguments

    Kwargs:
        cfunc (func): Receives a key and should return `True`
            if overlapping values should be combined. If a key occurs in
            multiple dicts and isn't combined, it will be overwritten
            by the last dict. Requires that `op` is set.

        op (func): Receives a list of 2 values from overlapping keys and should
            return the combined value. Common operators are `sum`, `min`,
            `max`, etc. Requires that `cfunc` is set. If a key is not present
            in all dicts, the value from `default` will be used. Note, since
            `op` applied inside of `reduce`, it may not perform as
            expected for all functions for more than 2 dicts. E.g. an average
            function will be applied as follows:

                ave([1, 2, 3]) --> ave([ave([1, 2]), 3])

            You would expect to get 2, but will instead get 2.25.

        default (int or str): default value to use in `op` for missing keys
            (default: 0).

    Returns:
        (List[str]): collapsed content

    Examples:
        >>> dicts = [{'a': 'item', 'amount': 200}, \
{'a': 'item', 'amount': 300}, {'a': 'item', 'amount': 400}]
        >>> cfunc = lambda k: k == 'amount'
        >>> merge_dicts(*dicts, cfunc=cfunc, op=sum)
        {u'a': u'item', u'amount': 900}
        >>> merge_dicts(*dicts)
        {u'a': u'item', u'amount': 400}
        >>> items = merge_dicts({'a': 1, 'b': 2}, {'b': 10, 'c': 11}).items()
        >>> sorted(items)
        [(u'a', 1), (u'b', 10), (u'c', 11)]
        >>> dicts = [{'a':1, 'b': 2, 'c': 3}, {'b': 4, 'c': 5, 'd': 6}]
        >>>
        >>> # Combine all keys
        >>> cfunc = lambda x: True
        >>> items = merge_dicts(*dicts, cfunc=cfunc, op=sum).items()
        >>> sorted(items)
        [(u'a', 1), (u'b', 6), (u'c', 8), (u'd', 6)]
        >>> fltrer = lambda x: x is not None
        >>> first = lambda x: filter(fltrer, x)[0]
        >>> kwargs = {'cfunc': cfunc, 'op': first, 'default': None}
        >>> items = merge_dicts(*dicts, **kwargs).items()
        >>> sorted(items)
        [(u'a', 1), (u'b', 2), (u'c', 3), (u'd', 6)]
        >>>
        >>> # This will only reliably give the expected result for 2 dicts
        >>> average = lambda x: sum(filter(fltrer, x)) / len(filter(fltrer, x))
        >>> kwargs = {'cfunc': cfunc, 'op': average, 'default': None}
        >>> items = merge_dicts(*dicts, **kwargs).items()
        >>> sorted(items)
        [(u'a', 1), (u'b', 3.0), (u'c', 4.0), (u'd', 6.0)]
        >>>
        >>> # Only combine key 'b'
        >>> cfunc = lambda k: k == 'b'
        >>> items = merge_dicts(*dicts, cfunc=cfunc, op=sum).items()
        >>> sorted(items)
        [(u'a', 1), (u'b', 6), (u'c', 5), (u'd', 6)]
        >>>
        >>> # This will reliably work for any number of dicts
        >>> from collections import defaultdict
        >>>
        >>> counted = defaultdict(int)
        >>> dicts = [{'a': 1, 'b': 4, 'c': 0}, {'a': 2, 'b': 5, 'c': 2}, \
{'a': 3, 'b': 6, 'd': 7}]
        >>> for d in dicts:
        ...     for k in d.keys():
        ...         counted[k] += 1
        ...
        >>> sorted(counted.items())
        [(u'a', 3), (u'b', 3), (u'c', 2), (u'd', 1)]
        >>> cfunc = lambda x: True
        >>> divide = lambda x: x[0] / x[1]
        >>> summed = merge_dicts(*dicts, cfunc=cfunc, op=sum)
        >>> sorted(summed.items())
        [(u'a', 6), (u'b', 15), (u'c', 2), (u'd', 7)]
        >>> items = merge_dicts(summed, counted, cfunc=cfunc, op=divide).items()
        >>> sorted(items)
        [(u'a', 2.0), (u'b', 5.0), (u'c', 1.0), (u'd', 7.0)]
    """
    cfunc = kwargs.get('cfunc')
    op = kwargs.get('op')
    default = kwargs.get('default', 0)

    def reducer(x, y):
        merge = lambda k, v: op([x.get(k, default), v]) if cfunc(k) else v
        new_y = ([k, merge(k, v)] for k, v in y.iteritems())
        return dict(it.chain(x.iteritems(), new_y))

    if cfunc and op:
        new_dict = reduce(reducer, dicts)
    else:
        new_dict = dict(it.chain.from_iterable(it.imap(dict.iteritems, dicts)))

    return new_dict
