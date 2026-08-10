// AgentAction.h

#ifndef ABM_AGENT_AGENT_ACTION_H
#define ABM_AGENT_AGENT_ACTION_H

#include <cstdint>

namespace abm {

/**
 * Behavioural trading action selected before order construction.
 *
 * This action is shared by heterogeneous agent strategies because buy, sell,
 * and hold decisions are model-level behavioural states. It remains separate
 * from OrderType because only buy and sell actions can become executable market
 * orders, while hold explicitly means the agent elects not to trade.
 */
enum class AgentAction : std::uint8_t { Buy, Sell, Hold };

} // namespace abm

#endif // ABM_AGENT_AGENT_ACTION_H
