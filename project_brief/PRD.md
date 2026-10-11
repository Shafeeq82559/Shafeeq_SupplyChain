# AI-Powered Supply Chain Disruption Assistant

## Overview

Supply chain teams regularly face disruptions caused by supplier issues, natural events, operational failures, labor problems, and other unexpected events. These disruptions can lead to production losses, financial impact, delayed recovery, and changes in suppliers. Operations teams need to analyze historical disruptions, identify similar cases, understand their impact, evaluate previous response strategies, and determine appropriate recovery actions. Manually searching through historical disruption records can be time-consuming and inconsistent.

## Example Professional Questions

- Has a similar supply chain disruption occurred previously, and how was it resolved?
- What factors are associated with higher production impact or financial loss?
- Which response strategies have been effective for similar disruptions, and how quickly were operations recovered?

Instead of manually searching through historical supply chain disruption records, build an AI-powered assistant that can retrieve similar disruption cases, analyze their impact, identify effective response strategies, and support disruption recovery decisions.

Build a semantic retrieval and AI-assisted supply chain disruption analysis system that can help operations teams investigate, prioritize, respond to, and recover from supply chain disruptions.

## Requirement 1 – Basic

- Build a Basic RAG system for historical supply chain disruption similarity search
- Implement hybrid search using keyword and semantic retrieval
- Build a supply chain disruption classification agent
- Implement metadata filtering based on disruption type, industry, supplier tier, supplier region, and disruption severity
- Generate basic disruption response and recovery recommendations based on historical cases
- Implement input validation guardrails
- Implement disruption prioritization based on severity, production impact, and financial loss
- Expose the core functionality through API endpoints.

## Requirement 2 – Advanced

- Implement DeepEval for evaluating disruption-analysis and recommendation quality
- Build production-impact, financial-loss, and recovery-time prediction models
- Implement LLM-as-Judge for validating disruption analysis and response recommendations
- Build a multi-agent supply chain workflow for disruption investigation, impact assessment, response planning, and recovery analysis
- Implement supply chain resilience and disruption-risk prediction
- Perform explainable analysis of disruption factors and their impact on production, financial loss, and recovery
- Implement a feedback loop for continuous improvement
- Build a simple front-end interface.

## Deliverables

1. Architecture Diagram
2. Design
3. Full Executable Code (Microservice)
4. Panel Presentation (10 minutes)

## Dataset

**Dataset Name:** Supply Chain Disruption and Recovery Dataset

**Primary Link:** Supply Chain Disruption and Recovery Dataset – Kaggle

**Alternative Link:** Supply Chain Disruption and Recovery Dataset – Kaggle

**Format:** CSV

**Key Fields:** disruption_id, disruption_type, industry, supplier_tier, supplier_region, supplier_size, has_backup_supplier, disruption_severity, production_impact_pct, revenue_loss_usd, response_type, response_time_days, partial_recovery_days, full_recovery_days, permanent_supplier_change

**Reason:** The dataset contains historical supply chain disruption events along with disruption type, industry, supplier characteristics, severity, production impact, financial loss, response strategy, response time, and recovery periods. These fields support semantic retrieval, hybrid search, disruption classification, metadata filtering, response recommendation, disruption prioritization, impact analysis, recovery-time prediction, resilience analysis, explainability, and AI-assisted disruption recovery workflows.
