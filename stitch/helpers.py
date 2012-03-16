import collections


def update(d, u):
    """
    Utility function that takes a dictionary and updates keys with values from a
    second dictionary.
    http://stackoverflow.com/a/3233356
    """
    for k, v in u.iteritems():
        if isinstance(v, collections.Mapping):
            r = update(d.get(k, {}), v)
            d[k] = r
        else:
            d[k] = u[k]
    return d
