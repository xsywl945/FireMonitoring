package com.firemonitoring.api.service;

import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.repository.CameraRepository;
import com.firemonitoring.api.repository.ZoneCameraBindingRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URI;
import java.time.Instant;
import java.util.List;

@Service
public class CameraService {
    private final CameraRepository cameras;
    private final ZoneCameraBindingRepository bindings;
    private final String whepBaseUrl;
    private final String hlsBaseUrl;
    private final long ticketTtlSeconds;

    public CameraService(CameraRepository cameras, ZoneCameraBindingRepository bindings,
                         @Value("${app.media.whep-base-url}") String whepBaseUrl,
                         @Value("${app.media.hls-base-url}") String hlsBaseUrl,
                         @Value("${app.media.ticket-ttl-seconds}") long ticketTtlSeconds) {
        this.cameras = cameras;
        this.bindings = bindings;
        this.whepBaseUrl = stripSlash(whepBaseUrl);
        this.hlsBaseUrl = stripSlash(hlsBaseUrl);
        this.ticketTtlSeconds = ticketTtlSeconds;
    }

    @Transactional(readOnly = true)
    public List<CameraResponse> list() { return cameras.findAll().stream().map(this::map).toList(); }

    @Transactional
    public CameraResponse update(Long id, CameraUpsert request) {
        CameraEntity camera = get(id);
        String source = blankToNull(request.sourceUri());
        // A blank address while editing keeps an existing masked RTSP credential.
        if (source == null && request.sourceType() == camera.getSourceType()) source = camera.getSourceUri();
        validateSource(request.sourceType(), source);
        camera.update(request.name().trim(), request.sourceType(), source, request.targetFps());
        return map(cameras.save(camera));
    }

    @Transactional
    public void delete(Long id) {
        CameraEntity camera = get(id);
        bindings.deleteAllByCameraId(id);
        bindings.flush();
        cameras.delete(camera);
    }

    private void validateSource(SourceType type, String source) {
        if ((type == SourceType.NETWORK_RTSP || type == SourceType.DEMO_FILE) && source == null)
            throw new BadRequestException("请填写视频地址");
        if (type == SourceType.NETWORK_RTSP) {
            try {
                URI uri = URI.create(source);
                if (!"rtsp".equalsIgnoreCase(uri.getScheme()) || uri.getHost() == null)
                    throw new IllegalArgumentException();
            } catch (IllegalArgumentException exception) {
                throw new BadRequestException("RTSP 地址格式不正确");
            }
        }
        if ((type == SourceType.INTEGRATED || type == SourceType.USB)
                && source != null && !source.matches("\\d{1,2}"))
            throw new BadRequestException("设备编号应为 0 到 99");
    }

    @Transactional
    public CameraResponse create(CameraUpsert request) {
        String sourceUri = blankToNull(request.sourceUri());
        validateSource(request.sourceType(), sourceUri);
        return map(cameras.save(new CameraEntity(request.name().trim(), request.sourceType(), sourceUri, request.targetFps())));
    }

    @Transactional
    public CameraProbeResult probe(Long id) {
        CameraEntity camera = get(id);
        Instant checkedAt = Instant.now();
        boolean valid;
        try { validateSource(camera.getSourceType(), camera.getSourceUri()); valid = true; }
        catch (BadRequestException exception) { valid = false; }
        return new CameraProbeResult(false, valid, checkedAt, null, null, null,
                valid ? "配置有效，连接状态以视频画面为准" : "视频地址未配置");
    }

    @Transactional(readOnly = true)
    public StreamTicket createStreamTicket(Long id) {
        CameraEntity camera = get(id);
        Instant expiresAt = Instant.now().plusSeconds(ticketTtlSeconds);
        return new StreamTicket(expiresAt,
                URI.create(whepBaseUrl + "/raw/" + camera.getStreamKey() + "/whep"),
                URI.create(hlsBaseUrl + "/raw/" + camera.getStreamKey() + "/index.m3u8"));
    }

    private CameraEntity get(Long id) {
        return cameras.findById(id).orElseThrow(() -> new ResourceNotFoundException("Camera not found: " + id));
    }

    private CameraResponse map(CameraEntity camera) {
        var binding = bindings.findByCameraId(camera.getId());
        return new CameraResponse(camera.getId(), camera.getName(), camera.getSourceType(), camera.getStreamKey(),
                mask(camera.getSourceUri()), camera.getStatus(), camera.getLastSeenAt(),
                binding.map(item -> item.getZone().getId()).orElse(null),
                binding.map(ZoneCameraBindingEntity::getViewRole).orElse(null), camera.getTargetFps());
    }

    private static String mask(String source) {
        if (source == null || source.isBlank()) return null;
        try {
            URI uri = URI.create(source);
            if (uri.getScheme() == null) return source;
            if (uri.getUserInfo() == null) return uri.getScheme() + "://" + uri.getHost()
                    + (uri.getPort() > 0 ? ":" + uri.getPort() : "") + (uri.getPath() == null ? "" : uri.getPath());
            return uri.getScheme() + "://***:***@" + uri.getHost()
                    + (uri.getPort() > 0 ? ":" + uri.getPort() : "") + (uri.getPath() == null ? "" : uri.getPath());
        } catch (IllegalArgumentException ignored) {
            return "***";
        }
    }

    private static String stripSlash(String value) { return value.replaceAll("/+$", ""); }
    private static String blankToNull(String value) { return value == null || value.isBlank() ? null : value.trim(); }
}
