// SocialInfluenceModel.cpp

#include "Simulation/SocialInfluenceModel.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <functional>
#include <unordered_map>
#include <vector>

namespace abm {
namespace {

double interactionWeight(double distance) {
    /*
     * Formula note:
     * omega_ij = 1 / (1 + d_ij).
     *
     * Nearby agents therefore have larger social influence while every
     * neighbour inside the interaction radius keeps a strictly positive weight.
     */
    return 1.0 / (1.0 + distance);
}

struct SocialGridCell {
    long long xIndex{0};
    long long yIndex{0};

    bool operator==(const SocialGridCell& other) const {
        return xIndex == other.xIndex && yIndex == other.yIndex;
    }
};

struct SocialGridCellHash {
    std::size_t operator()(const SocialGridCell& cell) const {
        const std::size_t xHash = std::hash<long long>{}(cell.xIndex);
        const std::size_t yHash = std::hash<long long>{}(cell.yIndex);
        return xHash ^ (yHash + 0x9e3779b97f4a7c15ULL + (xHash << 6U) + (xHash >> 2U));
    }
};

SocialGridCell socialGridCellFor(const Agent& agent, double cellSize) {
    return {static_cast<long long>(std::floor(agent.getXCoordinate() / cellSize)),
            static_cast<long long>(std::floor(agent.getYCoordinate() / cellSize))};
}

using SocialGrid = std::unordered_map<SocialGridCell, std::vector<std::size_t>, SocialGridCellHash>;

struct SocialPairCandidate {
    std::size_t lhsId{0};
    std::size_t rhsId{0};
    double interactionRadius{0.0};
};

Agent* agentById(const std::vector<Agent*>& agentsById, std::size_t agentId) {
    if (agentId >= agentsById.size()) {
        return nullptr;
    }
    return agentsById.at(agentId);
}

void addNeighbourIfInsideRadius(const SimulationPopulation& population,
                                const SocialPairCandidate& candidate,
                                std::vector<std::vector<SocialNeighbor>>& socialNeighbors) {
    if (candidate.lhsId >= candidate.rhsId) {
        return;
    }

    const Agent* lhs = agentById(population.agentsById, candidate.lhsId);
    const Agent* rhs = agentById(population.agentsById, candidate.rhsId);
    if (lhs == nullptr || rhs == nullptr) {
        return;
    }

    const double distance = std::hypot(lhs->getXCoordinate() - rhs->getXCoordinate(),
                                       lhs->getYCoordinate() - rhs->getYCoordinate());
    if (distance > candidate.interactionRadius) {
        return;
    }

    const double weight = interactionWeight(distance);
    socialNeighbors.at(candidate.lhsId)
        .push_back(SocialNeighbor{static_cast<std::uint32_t>(candidate.rhsId), weight});
    socialNeighbors.at(candidate.rhsId)
        .push_back(SocialNeighbor{static_cast<std::uint32_t>(candidate.lhsId), weight});
}

void assignSocialProfiles(const SimulationPopulation& population,
                          const SocialInfluenceConfig& config, RandomEngine& random) {
    for (std::size_t agentId = 1; agentId < population.agentsById.size(); ++agentId) {
        Agent* agent = agentById(population.agentsById, agentId);
        if (agent == nullptr) {
            continue;
        }

        agent->setSocialProfile(
            random.generateUniformDist(0.0, config.spaceWidth),
            random.generateUniformDist(0.0, config.spaceHeight),
            random.generateUniformDist(config.gammaMin, config.gammaMax),
            random.generateUniformDist(config.privateSignalStdMin, config.privateSignalStdMax));
        agent->setOpinions(0.0, 0.0);
    }
}

SocialGrid buildSocialGrid(const SimulationPopulation& population, double interactionRadius) {
    SocialGrid grid;
    grid.reserve(population.agentsById.size());

    for (std::size_t agentId = 1; agentId < population.agentsById.size(); ++agentId) {
        const Agent* agent = agentById(population.agentsById, agentId);
        if (agent == nullptr) {
            continue;
        }
        auto cellIt = grid.try_emplace(socialGridCellFor(*agent, interactionRadius)).first;
        cellIt->second.push_back(agentId);
    }

    return grid;
}

void connectSocialNeighbours(const SimulationPopulation& population, const SocialGrid& grid,
                             double interactionRadius,
                             std::vector<std::vector<SocialNeighbor>>& socialNeighbors) {
    for (const auto& cellEntry : grid) {
        const SocialGridCell& cell = cellEntry.first;
        const std::vector<std::size_t>& agentIds = cellEntry.second;
        for (int xOffset = -1; xOffset <= 1; ++xOffset) {
            for (int yOffset = -1; yOffset <= 1; ++yOffset) {
                const SocialGridCell neighbourCell{cell.xIndex + xOffset, cell.yIndex + yOffset};
                const auto neighbourCellEntry = grid.find(neighbourCell);
                if (neighbourCellEntry == grid.end()) {
                    continue;
                }

                for (const std::size_t lhsId : agentIds) {
                    for (const std::size_t rhsId : neighbourCellEntry->second) {
                        addNeighbourIfInsideRadius(
                            population, SocialPairCandidate{lhsId, rhsId, interactionRadius},
                            socialNeighbors);
                    }
                }
            }
        }
    }
}

void sortSocialNeighbours(std::vector<std::vector<SocialNeighbor>>& socialNeighbors) {
    for (std::vector<SocialNeighbor>& neighbours : socialNeighbors) {
        std::sort(neighbours.begin(), neighbours.end(),
                  [](const SocialNeighbor& lhs, const SocialNeighbor& rhs) {
                      return lhs.agentId < rhs.agentId;
                  });
    }
}

} // namespace

void SocialInfluenceModel::initialize(const SimulationPopulation& population,
                                      const SocialInfluenceConfig& config, RandomEngine& random) {
    socialNeighbors_.assign(population.agentsById.size(), {});
    assignSocialProfiles(population, config, random);

    if (!config.enabled || config.interactionRadius <= 0.0) {
        return;
    }

    const SocialGrid grid = buildSocialGrid(population, config.interactionRadius);
    connectSocialNeighbours(population, grid, config.interactionRadius, socialNeighbors_);
    sortSocialNeighbours(socialNeighbors_);
}

void SocialInfluenceModel::prepareForRun(const SimulationPopulation& population) {
    nextOpinionScratch_.assign(population.agentsById.size(), 0.0);
}

void SocialInfluenceModel::updateOpinions(const SimulationPopulation& population,
                                          const SocialInfluenceConfig& config,
                                          RandomEngine& random) {
    if (population.agentsById.empty()) {
        return;
    }

    if (!config.enabled) {
        return;
    }

    if (nextOpinionScratch_.size() != population.agentsById.size()) {
        nextOpinionScratch_.resize(population.agentsById.size(), 0.0);
    }
    std::fill(nextOpinionScratch_.begin(), nextOpinionScratch_.end(), 0.0);

    for (std::size_t agentId = 1; agentId < population.agentsById.size(); ++agentId) {
        Agent* agent = agentById(population.agentsById, agentId);
        if (agent == nullptr) {
            continue;
        }

        double weightedOpinionSum = 0.0;
        double totalWeight = 0.0;
        for (const SocialNeighbor& neighbor : socialNeighbors_.at(agentId)) {
            Agent* neighborAgent = agentById(population.agentsById, neighbor.agentId);
            if (neighborAgent == nullptr) {
                continue;
            }

            weightedOpinionSum += neighbor.weight * neighborAgent->getPreviousOpinion();
            totalWeight += neighbor.weight;
        }

        /*
         * Formula note:
         * S_i,t = sum_j omega_ij * o_j,t-1 / sum_j omega_ij,
         * eta_i,t ~ Normal(0, sigma_private_i^2),
         * o_i,t = gamma_i * S_i,t + (1 - gamma_i) * eta_i,t.
         *
         * The model keeps synchronous updating by reading previous opinions
         * into S_i,t and storing the next opinions in a scratch vector.
         */
        const double socialSignal = totalWeight > 0.0 ? (weightedOpinionSum / totalWeight) : 0.0;
        const double privateSignal =
            agent->getPrivateSignalStdDev() > 0.0
                ? random.generateNormalDist(0.0, agent->getPrivateSignalStdDev())
                : 0.0;
        nextOpinionScratch_.at(agentId) = (agent->getSocialGamma() * socialSignal) +
                                          ((1.0 - agent->getSocialGamma()) * privateSignal);
    }

    for (std::size_t agentId = 1; agentId < population.agentsById.size(); ++agentId) {
        Agent* agent = agentById(population.agentsById, agentId);
        if (agent != nullptr) {
            const double nextOpinion = nextOpinionScratch_.at(agentId);
            agent->setOpinions(nextOpinion, nextOpinion);
        }
    }
}

} // namespace abm
