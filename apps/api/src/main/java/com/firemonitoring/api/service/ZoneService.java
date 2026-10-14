package com.firemonitoring.api.service;

import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.repository.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.*;

@Service
public class ZoneService {
    private final ZoneRepository zones;
    private final CameraRepository cameras;
    private final ZoneCameraBindingRepository bindings;
    private final IncidentRepository incidents;

    public ZoneService(ZoneRepository zones, CameraRepository cameras, ZoneCameraBindingRepository bindings,
                       IncidentRepository incidents) {
        this.zones = zones;
        this.cameras = cameras;
        this.bindings = bindings;
        this.incidents = incidents;
    }

    @Transactional(readOnly = true)
    public List<ZoneResponse> list() {
        return zones.findAll().stream().filter(zone -> zone.getStatus() == ZoneStatus.ENABLED)
                .map(ZoneService::map).toList();
    }

    @Transactional
    public ZoneResponse create(ZoneUpsert request) {
        String name = request.name().trim();
        if (zones.existsByName(name)) throw new ConflictException("教室名称已存在");
        return map(zones.save(new ZoneEntity(name, request.sceneType())));
    }

    @Transactional
    public ZoneResponse update(Long id, ZoneUpsert request) {
        ZoneEntity zone = activeZone(id);
        String name = request.name().trim();
        if (zones.existsByNameAndIdNot(name, id)) throw new ConflictException("教室名称已存在");
        zone.update(name, request.sceneType());
        return map(zones.save(zone));
    }

    @Transactional
    public void delete(Long id) {
        ZoneEntity zone = activeZone(id);
        bindings.deleteAllByZoneId(id);
        if (incidents.existsByZoneId(id)) {
            zone.disable();
            zones.save(zone);
        } else {
            bindings.flush();
            zones.delete(zone);
        }
    }

    private ZoneEntity activeZone(Long id) {
        return zones.findById(id).filter(zone -> zone.getStatus() == ZoneStatus.ENABLED)
                .orElseThrow(() -> new ResourceNotFoundException("教室不存在"));
    }

    @Transactional
    public void replaceBindings(Long zoneId, List<CameraBindingRequest> requests) {
        ZoneEntity zone = activeZone(zoneId);
        Set<Long> cameraIds = new HashSet<>();
        Set<ViewRole> roles = new HashSet<>();
        for (CameraBindingRequest request : requests) {
            if (!cameraIds.add(request.cameraId())) throw new BadRequestException("A camera may only be bound once per zone");
            if (!roles.add(request.viewRole())) throw new BadRequestException("Each view role may only be used once per zone");
        }
        for (Long cameraId : cameraIds) {
            bindings.findByCameraId(cameraId).ifPresent(binding -> {
                if (!binding.getZone().getId().equals(zoneId))
                    throw new ConflictException("摄像头已绑定其他教室，请先解除绑定");
            });
        }
        Map<Long, CameraEntity> byId = new HashMap<>();
        cameras.findAllById(cameraIds).forEach(camera -> byId.put(camera.getId(), camera));
        if (byId.size() != cameraIds.size()) throw new ResourceNotFoundException("One or more cameras do not exist");
        bindings.deleteAllByZoneId(zoneId);
        bindings.flush();
        bindings.saveAll(requests.stream().map(request -> new ZoneCameraBindingEntity(
                zone, byId.get(request.cameraId()), request.viewRole(), request.weight())).toList());
    }

    private static ZoneResponse map(ZoneEntity zone) {
        return new ZoneResponse(zone.getId(), zone.getName(), zone.getSceneType(), zone.getStatus());
    }
}
