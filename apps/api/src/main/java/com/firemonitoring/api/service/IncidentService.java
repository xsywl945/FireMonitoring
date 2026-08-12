package com.firemonitoring.api.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.*;
import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.repository.*;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.*;
import java.security.MessageDigest;
import java.util.*;

@Service
public class IncidentService {
    private final IncidentRepository incidents;
    private final IncidentTimelineRepository timeline;
    private final CameraRepository cameras;
    private final IdempotencyRecordRepository idempotency;
    private final IncidentStateMachine stateMachine;
    private final ObjectMapper objectMapper;
    private final SimpMessagingTemplate messaging;

    public IncidentService(IncidentRepository incidents, IncidentTimelineRepository timeline,
                           CameraRepository cameras,
                           IdempotencyRecordRepository idempotency, IncidentStateMachine stateMachine,
                           ObjectMapper objectMapper, SimpMessagingTemplate messaging) {
        this.incidents = incidents;
        this.timeline = timeline;
        this.cameras = cameras;
        this.idempotency = idempotency;
        this.stateMachine = stateMachine;
        this.objectMapper = objectMapper;
        this.messaging = messaging;
    }

    @Transactional(readOnly = true)
    public List<IncidentSummary> list(IncidentStatus status, Severity severity) {
        List<IncidentEntity> result;
        if (status != null && severity != null) result = incidents.findByStatusAndSeverityOrderByStartedAtDesc(status, severity);
        else if (status != null) result = incidents.findByStatusOrderByStartedAtDesc(status);
        else if (severity != null) result = incidents.findBySeverityOrderByStartedAtDesc(severity);
        else result = incidents.findAllByOrderByStartedAtDesc();
        return result.stream().map(IncidentService::summary).toList();
    }

    @Transactional(readOnly = true)
    public IncidentDetail get(Long id) { return detail(find(id)); }

    @Transactional(readOnly = true)
    public String evidenceObjectKey(Long id, int index) {
        if (index < 0) throw new BadRequestException("Evidence index must be non-negative");
        List<JsonNode> observations = readArray(find(id).getObservationsJson());
        if (index >= observations.size()) {
            throw new ResourceNotFoundException("Evidence frame does not exist");
        }
        JsonNode value = observations.get(index).get("snapshotObjectKey");
        if (value == null || !value.isTextual() || value.asText().isBlank()) {
            throw new ResourceNotFoundException("Evidence image is not ready");
        }
        return value.asText();
    }

    @Transactional
    public IncidentDetail transition(Long id, UUID key, IncidentActionRequest request, String actor) {
        String fingerprint = fingerprint(request);
        var prior = idempotency.findByIdempotencyKey(key.toString());
        if (prior.isPresent()) {
            if (!prior.get().getIncidentId().equals(id) || prior.get().getRequestAction() != request.action()
                    || !prior.get().getRequestFingerprint().equals(fingerprint)) {
                throw new ConflictException("Idempotency-Key has already been used for another operation");
            }
            return readStoredResponse(prior.get().getResponseJson());
        }
        if (request.action() == IncidentAction.MARK_FALSE_ALARM && request.falseAlarmReason() == null) {
            throw new BadRequestException("falseAlarmReason is required when marking a false alarm");
        }
        IncidentEntity incident = find(id);
        IncidentStatus target = stateMachine.target(incident.getStatus(), request.action());
        Instant now = Instant.now();
        incident.transitionTo(target, now);
        incidents.save(incident);
        timeline.save(new IncidentTimelineEntity(incident, request.action().name(), blankToNull(request.note()),
                request.falseAlarmReason(), actor, now));
        IncidentDetail result = detail(incident);
        idempotency.save(new IdempotencyRecordEntity(key, id, request.action(), fingerprint, target, writeResponse(result)));
        messaging.convertAndSend("/topic/incidents", result);
        return result;
    }

    private IncidentEntity find(Long id) {
        return incidents.findById(id).orElseThrow(() -> new ResourceNotFoundException("Incident not found: " + id));
    }

    private IncidentDetail detail(IncidentEntity incident) {
        List<IncidentObservationDetail> observations = mapObservations(incident);
        JsonNode semantic = mapSemantic(readNode(incident.getSemanticAnalysisJson()));
        List<Map<String, Object>> entries = timeline.findByIncidentIdOrderByOccurredAtAsc(incident.getId()).stream()
                .map(item -> {
                    Map<String, Object> value = new LinkedHashMap<>();
                    value.put("id", item.getId());
                    value.put("action", timelineLabel(item.getEventType()));
                    value.put("note", item.getNote());
                    value.put("falseAlarmReason", item.getFalseAlarmReason());
                    value.put("actor", item.getActorUsername());
                    value.put("occurredAt", item.getOccurredAt());
                    return value;
                }).toList();
        return new IncidentDetail(incident.getId(), incident.getZone().getId(), incident.getZone().getName(),
                incident.getStatus(), incident.getSeverity(), incident.getPrimaryType(), incident.getStartedAt(),
                incident.getAcknowledgedAt(), incident.getFusionScore(), observations, semantic, entries);
    }

    private List<IncidentObservationDetail> mapObservations(IncidentEntity incident) {
        List<JsonNode> values = readArray(incident.getObservationsJson());
        List<IncidentObservationDetail> result = new ArrayList<>();
        for (int index = 0; index < values.size(); index++) {
            JsonNode value = values.get(index);
            Long cameraId = longValue(value, "cameraId");
            String cameraName = cameraId == null ? "未命名摄像头" : cameras.findById(cameraId)
                    .map(CameraEntity::getName).orElse("摄像头 #" + cameraId);
            String role = textValue(value, "viewRole", "SINGLE");
            Instant capturedAt = instantValue(value, "capturedAt",
                    incident.getConfirmedAt() == null ? incident.getStartedAt() : incident.getConfirmedAt());
            List<JsonNode> detections = new ArrayList<>();
            JsonNode detectionValues = value.get("detections");
            if (detectionValues != null && detectionValues.isArray()) {
                detectionValues.forEach(detections::add);
            }
            double temporalScore = numberValue(value, "temporalScore",
                    numberValue(value, "score", incident.getFusionScore() == null ? 0.0 : incident.getFusionScore()));
            result.add(new IncidentObservationDetail(
                    cameraId + "-" + index,
                    cameraId,
                    role,
                    capturedAt,
                    cameraName,
                    intValue(value, "imageWidth", 640),
                    intValue(value, "imageHeight", 480),
                    detections,
                    temporalScore,
                    value.hasNonNull("snapshotObjectKey") && !value.get("snapshotObjectKey").asText().isBlank()));
        }
        return result;
    }

    private JsonNode mapSemantic(JsonNode raw) {
        if (raw == null || !raw.isObject()) return null;
        var result = objectMapper.createObjectNode();
        String status = textValue(raw, "status", "FAILED");
        result.put("state", "SUCCEEDED".equals(status) ? "COMPLETED" : "FAILED");
        copyText(raw, result, "reasoningSummary", "summary");
        copyText(raw, result, "sourceNature", "sourceNature");
        copyText(raw, result, "riskLevel", "sceneRisk");
        copyText(raw, result, "model", "model");
        copyText(raw, result, "errorCode", "errorCode");
        if (raw.hasNonNull("confidence")) result.set("confidence", raw.get("confidence"));
        if (raw.has("recommendedActions")) result.set("recommendations", raw.get("recommendedActions"));
        JsonNode uncertainties = raw.get("uncertainties");
        if (uncertainties != null && uncertainties.isArray()) {
            List<String> values = new ArrayList<>();
            uncertainties.forEach(item -> values.add(item.asText()));
            if (!values.isEmpty()) result.put("uncertainty", String.join("；", values));
        }
        return result;
    }

    private static void copyText(JsonNode source, com.fasterxml.jackson.databind.node.ObjectNode target,
                                 String sourceName, String targetName) {
        if (source.hasNonNull(sourceName)) target.put(targetName, source.get(sourceName).asText());
    }

    private static Long longValue(JsonNode value, String name) {
        JsonNode field = value.get(name);
        return field == null || !field.canConvertToLong() ? null : field.asLong();
    }

    private static int intValue(JsonNode value, String name, int fallback) {
        JsonNode field = value.get(name);
        return field == null || !field.canConvertToInt() ? fallback : field.asInt();
    }

    private static double numberValue(JsonNode value, String name, double fallback) {
        JsonNode field = value.get(name);
        return field == null || !field.isNumber() ? fallback : field.asDouble();
    }

    private static String textValue(JsonNode value, String name, String fallback) {
        JsonNode field = value.get(name);
        return field == null || !field.isTextual() || field.asText().isBlank() ? fallback : field.asText();
    }

    private static Instant instantValue(JsonNode value, String name, Instant fallback) {
        try {
            JsonNode field = value.get(name);
            return field == null || !field.isTextual() ? fallback : Instant.parse(field.asText());
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private static String timelineLabel(String eventType) {
        return switch (eventType) {
            case "INCIDENT_CONFIRMED" -> "模型确认预警";
            case "INCIDENT_EVIDENCE_READY" -> "关键帧已归档";
            case "VLM_ANALYSIS_COMPLETED" -> "语义研判完成";
            case "VLM_ANALYSIS_FAILED" -> "语义研判失败";
            case "ACKNOWLEDGE" -> "人工确认";
            case "START_HANDLING" -> "开始处置";
            case "RESOLVE" -> "事件解决";
            case "MARK_FALSE_ALARM" -> "标记误报";
            default -> eventType;
        };
    }

    private List<JsonNode> readArray(String json) {
        if (json == null || json.isBlank()) return List.of();
        try { return objectMapper.readValue(json, new TypeReference<>() {}); }
        catch (Exception e) { return List.of(); }
    }

    private JsonNode readNode(String json) {
        if (json == null || json.isBlank()) return null;
        try { return objectMapper.readTree(json); }
        catch (Exception e) { return null; }
    }

    private String fingerprint(IncidentActionRequest request) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(objectMapper.writeValueAsBytes(request));
            return java.util.HexFormat.of().formatHex(digest);
        } catch (Exception exception) {
            throw new IllegalStateException("Unable to fingerprint idempotent request", exception);
        }
    }

    private String writeResponse(IncidentDetail response) {
        try { return objectMapper.writeValueAsString(response); }
        catch (Exception exception) { throw new IllegalStateException("Unable to store idempotent response", exception); }
    }

    private IncidentDetail readStoredResponse(String json) {
        try { return objectMapper.readValue(json, IncidentDetail.class); }
        catch (Exception exception) { throw new IllegalStateException("Unable to read idempotent response", exception); }
    }

    private static IncidentSummary summary(IncidentEntity incident) {
        return new IncidentSummary(incident.getId(), incident.getZone().getId(), incident.getZone().getName(),
                incident.getStatus(), incident.getSeverity(), incident.getPrimaryType(), incident.getStartedAt(),
                incident.getAcknowledgedAt());
    }

    private static String blankToNull(String value) { return value == null || value.isBlank() ? null : value.trim(); }
}
