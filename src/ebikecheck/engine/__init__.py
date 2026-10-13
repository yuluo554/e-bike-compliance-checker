"""引擎层：确定性判定内核（零第三方依赖）。

模块依赖方向：``findings`` ← ``values`` ← ``rules`` / ``matrix`` / ``version``。
引擎层不得 import 表现层或任何第三方包。
"""
