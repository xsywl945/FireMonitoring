package com.firemonitoring.api.web;

import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.service.IncidentService;
import jakarta.validation.Valid;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.*;

@RestController
@RequestMapping("/api/v1/incidents")
public class IncidentController {
    private final IncidentService incidents;

    public IncidentController(IncidentService incidents) { this.incidents = incidents; }

    @GetMapping
    public List<IncidentSummary> list(@RequestParam(required = false) IncidentStatus status,
                                      @RequestParam(required = false) Severity severity) {
        return incidents.list(status, severity);
    }

    @GetMapping("/{incidentId}")
    public IncidentDetail detail(@PathVariable Long incidentId) { return incidents.get(incidentId); }

    @PostMapping("/{incidentId}/actions")
    @PreAuthorize("hasAnyRole('ADMIN', 'OPERATOR')")
    public IncidentDetail transition(@PathVariable Long incidentId,
                                     @RequestHeader("Idempotency-Key") UUID idempotencyKey,
                                     @Valid @RequestBody IncidentActionRequest request,
                                     Authentication authentication) {
        return incidents.transition(incidentId, idempotencyKey, request, authentication.getName());
    }
}
