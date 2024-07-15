from autogpt_server.blocks.basic import ConstantBlock, PrintingBlock
from autogpt_server.blocks.text import TextFormatterBlock
from autogpt_server.data import graph
from autogpt_server.data.graph import create_graph
from autogpt_server.util.test import SpinTestServer, wait_execution


def create_test_graph() -> graph.Graph:
    """
    ConstantBlock
                \
                 ---- TextFormatterBlock ---- PrintingBlock
                /
    ConstantBlock
    """
    nodes = [
        graph.Node(block_id=ConstantBlock().id),
        graph.Node(block_id=ConstantBlock().id),
        graph.Node(
            block_id=TextFormatterBlock().id,
            input_default={
                "format": "{texts[0]},{texts[1]},{texts[2]}",
                "texts_$_3": "!!!",
            },
        ),
        graph.Node(block_id=PrintingBlock().id),
    ]
    links = [
        graph.Link(nodes[0].id, nodes[2].id, "output", "texts_$_1"),
        graph.Link(nodes[1].id, nodes[2].id, "output", "texts_$_2"),
        graph.Link(nodes[2].id, nodes[3].id, "output", "text"),
    ]

    return graph.Graph(
        name="TestGraph",
        description="Test graph",
        nodes=nodes,
        links=links,
    )


async def sample_agent():
    async with SpinTestServer() as server:
        exec_man = server.exec_manager
        test_graph = await create_graph(create_test_graph())
        input_data = {"input": "test!!"}
        response = await server.agent_server.execute_graph(test_graph.id, input_data)
        print(response)
        result = await wait_execution(exec_man, test_graph.id, response["id"], 4, 10)
        print(result)


if __name__ == "__main__":
    import asyncio
    asyncio.run(sample_agent())
