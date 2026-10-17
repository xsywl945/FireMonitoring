package com.firemonitoring.api.web;

import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.service.IncidentService;
import com.firemonitoring.api.service.EvidenceStorageService;
import org.springframework.web.bind.annotation.*;
import org.springframework.http.*;

import java.util.*;

@RestController
@RequestMapping("/api/v1/incidents")
public class IncidentController {
    private final IncidentService incidents;
    private final EvidenceStorageService evidence;

    public IncidentController(IncidentService incidents, EvidenceStorageService evidence) {
        this.incidents = incidents;
        this.evidence = evidence;
    }

    @GetMapping
    public List<IncidentSummary> list(@RequestParam(required = false) IncidentStatus status,
                                      @RequestParam(required = false) Severity severity) {
        return incidents.list(status, severity);
    }

    @GetMapping("/analyses")
    public List<IncidentAnalysis> analyses() { return incidents.analyses(); }

    @GetMapping("/{incidentId}")
    public IncidentDetail detail(@PathVariable Long incidentId) { return incidents.get(incidentId); }

    @GetMapping("/{incidentId}/evidence/{index}")
    public ResponseEntity<byte[]> evidence(@PathVariable Long incidentId, @PathVariable int index) {
        byte[] data = evidence.readJpeg(incidents.evidenceObjectKey(incidentId, index));
        return ResponseEntity.ok()
                .contentType(MediaType.IMAGE_JPEG)
                .cacheControl(CacheControl.noStore())
                .body(data);
    }

}
