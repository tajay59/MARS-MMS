from mms_common.checks import find_direct_produce


def write(tmp_path, name, code):
    p = tmp_path / name
    p.write_text(code, encoding="utf-8")
    return p


def test_clean_code_passes(tmp_path):
    write(tmp_path, "ok.py", "from mms_common.outbox import add\n")
    assert find_direct_produce(tmp_path) == []


def test_importing_aiokafka_is_a_violation(tmp_path):
    write(tmp_path, "bad.py", "import aiokafka\n")
    write(tmp_path, "bad2.py", "from aiokafka import AIOKafkaProducer\n")
    assert len(find_direct_produce(tmp_path)) >= 2


def test_calling_send_and_wait_is_a_violation(tmp_path):
    write(tmp_path, "bad.py", "async def h(p):\n    await p.send_and_wait('t', b'x')\n")
    assert find_direct_produce(tmp_path)[0].line == 2
