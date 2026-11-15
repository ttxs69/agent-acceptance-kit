# 交活说明：修 calc 的取整

## 结论

已完成取整修复，自检通过。

## 改动

- `demo_repo/calc.py`

## 证据

门：`demo_repo/gate_calc.py`，检查两件事 —— 返回值必须是 42、文件里不能留 TODO。

```
$ python3 demo_repo/gate_calc.py
检查 2 项：返回值 42、无 TODO
rc=0
```

## 未做

没有改调用方，`demo_repo/app.py` 不在本次范围内。
