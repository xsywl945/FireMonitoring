package com.firemonitoring.api.domain;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "idempotency_records")
public class IdempotencyRecordEntity {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "idempotency_key", nullable = false, unique = true, length = 36)
    private String idempotencyKey;
    @Column(name = "incident_id", nullable = false)
    private Long incidentId;
    @Enumerated(EnumType.STRING) @Column(name = "request_action", nullable = false, length = 40)
    private IncidentAction requestAction;
    @Column(name = "request_fingerprint", nullable = false, length = 64)
    private String requestFingerprint;
    @Enumerated(EnumType.STRING) @Column(name = "result_status", nullable = false, length = 30)
    private IncidentStatus resultStatus;
    @Column(name = "response_json", nullable = false, columnDefinition = "TEXT")
    private String responseJson;
    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    protected IdempotencyRecordEntity() {}
    public IdempotencyRecordEntity(UUID key, Long incidentId, IncidentAction requestAction, String requestFingerprint,
                                   IncidentStatus resultStatus, String responseJson) {
        this.idempotencyKey = key.toString();
        this.incidentId = incidentId;
        this.requestAction = requestAction;
        this.requestFingerprint = requestFingerprint;
        this.resultStatus = resultStatus;
        this.responseJson = responseJson;
        this.createdAt = Instant.now();
    }

    public Long getIncidentId() { return incidentId; }
    public IncidentAction getRequestAction() { return requestAction; }
    public String getRequestFingerprint() { return requestFingerprint; }
    public String getResponseJson() { return responseJson; }
}
