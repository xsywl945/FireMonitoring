package com.firemonitoring.api.events;

import java.util.List;

public record IncidentEvidenceReadyPayload(List<EvidenceFramePayload> evidence) {}
