from sessionbin.adapters.common import attach_results
from sessionbin.schema.types import Block, Turn


def tool_call(call_id: str, name: str = "bash") -> Block:
    return Block(kind="tool_use", tool_name=name, tool_input={}, tool_use_id=call_id)


def tool_result(call_id: str, output: str) -> Block:
    return Block(kind="tool_result", tool_use_id=call_id, tool_output=output)


def assistant_turn(*blocks: Block) -> Turn:
    return Turn(index=0, role="assistant", timestamp=None, blocks=list(blocks))


def shape(turn: Turn) -> list[str]:
    return [f"{b.kind}:{b.tool_use_id}" for b in turn.blocks]


class TestAttachResults:
    def test_result_follows_its_call(self):
        turn = assistant_turn(Block(kind="thinking", text=""), tool_call("c1"), tool_call("c2"))
        attach_results(turn, [tool_result("c1", "one")])
        attach_results(turn, [tool_result("c2", "two")])
        assert shape(turn) == [
            "thinking:None",
            "tool_use:c1",
            "tool_result:c1",
            "tool_use:c2",
            "tool_result:c2",
        ]

    def test_results_arriving_out_of_order_still_land_behind_their_calls(self):
        turn = assistant_turn(tool_call("c1"), tool_call("c2"), Block(kind="text", text="done"))
        attach_results(turn, [tool_result("c2", "two"), tool_result("c1", "one")])
        assert shape(turn) == [
            "tool_use:c1",
            "tool_result:c1",
            "tool_use:c2",
            "tool_result:c2",
            "text:None",
        ]

    def test_duplicated_call_id_pairs_in_order(self):
        turn = assistant_turn(
            tool_call("c1", "bash"), tool_call("c2", "read"), tool_call("c2", "read")
        )
        attach_results(
            turn, [tool_result("c1", "a"), tool_result("c2", "b"), tool_result("c2", "c")]
        )
        assert shape(turn) == [
            "tool_use:c1",
            "tool_result:c1",
            "tool_use:c2",
            "tool_result:c2",
            "tool_use:c2",
            "tool_result:c2",
        ]
        assert [b.tool_output for b in turn.blocks if b.kind == "tool_result"] == ["a", "b", "c"]

    def test_extra_results_collect_behind_the_last_call(self):
        turn = assistant_turn(tool_call("c1"))
        attach_results(turn, [tool_result("c1", "a"), tool_result("c1", "b")])
        assert [b.tool_output for b in turn.blocks[1:]] == ["a", "b"]

    def test_result_takes_the_tool_name_of_its_call(self):
        turn = assistant_turn(tool_call("c1", "read"), tool_call("c2", "write"))
        attach_results(turn, [tool_result("c2", "x")])
        assert turn.blocks[2].tool_name == "write"
