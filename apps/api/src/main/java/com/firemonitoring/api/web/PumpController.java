package com.firemonitoring.api.web;

import com.fasterxml.jackson.databind.JsonNode;
import com.firemonitoring.api.service.InferenceControlClient;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.util.Map;

@RestController
@RequestMapping("/api/v1/pump")
public class PumpController {
    private final InferenceControlClient inference;

    public PumpController(InferenceControlClient inference) { this.inference = inference; }

    @GetMapping
    public JsonNode status() { return inference.request("/pump", null); }

    @PostMapping("/stop")
    @PreAuthorize("hasAnyRole('ADMIN', 'OPERATOR')")
    public JsonNode stop() { return inference.request("/pump/stop", Map.of()); }
}
