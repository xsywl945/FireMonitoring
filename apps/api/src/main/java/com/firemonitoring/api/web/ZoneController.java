package com.firemonitoring.api.web;

import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.service.ZoneService;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import org.springframework.http.*;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@Validated
@RestController
@RequestMapping("/api/v1/zones")
public class ZoneController {
    private final ZoneService zones;

    public ZoneController(ZoneService zones) { this.zones = zones; }

    @GetMapping
    public List<ZoneResponse> list() { return zones.list(); }

    @PostMapping
    @PreAuthorize("hasAnyRole('ADMIN', 'OPERATOR')")
    public ResponseEntity<ZoneResponse> create(@Valid @RequestBody ZoneUpsert request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(zones.create(request));
    }

    @PutMapping("/{zoneId}/camera-bindings")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    @PreAuthorize("hasAnyRole('ADMIN', 'OPERATOR')")
    public void replaceBindings(@PathVariable Long zoneId,
                                @RequestBody @Size(min = 1, max = 2) List<@Valid CameraBindingRequest> requests) {
        zones.replaceBindings(zoneId, requests);
    }
}
