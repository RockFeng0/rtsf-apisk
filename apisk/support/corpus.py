#! python3
# -*- encoding: utf-8 -*-


import pytest


def sample_or_skip(sampler, *args, **kwargs):
    """调用采样函数；语料缺失时 ``pytest.skip`` 而非失败。

    采样器以 ``FileNotFoundError`` / ``RuntimeError`` 表达「语料不可用」，
    这两种异常都被视为环境问题，统一转成 skip。
    """
    try:
        return sampler(*args, **kwargs)
    except (FileNotFoundError, RuntimeError) as exc:
        pytest.skip(str(exc))


__all__ = ["sample_or_skip"]
