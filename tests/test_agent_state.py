from app.agent import AgentState, AgentStatus


def test_agent_state_defaults():
    state = AgentState()

    assert state.conversation == []
    assert state.iteration == 0
    assert state.status == AgentStatus.RUNNING
    assert state.final_response is None
    assert state.error is None
    assert state.is_finished is False


def test_agent_state_completed():
    state = AgentState(
        status=AgentStatus.COMPLETED,
        final_response="Done.",
    )

    assert state.is_finished is True
    assert state.final_response == "Done."


def test_agent_state_failed():
    state = AgentState(
        status=AgentStatus.FAILED,
        error="Tool execution failed.",
    )

    assert state.is_finished is True
    assert state.error == "Tool execution failed."


def test_agent_state_max_iterations():
    state = AgentState(
        status=AgentStatus.MAX_ITERATIONS,
        iteration=5,
    )

    assert state.is_finished is True
    assert state.iteration == 5
