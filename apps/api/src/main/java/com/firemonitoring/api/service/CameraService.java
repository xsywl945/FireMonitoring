package com.firemonitoring.api.service;

import com.firemonitoring.api.domain.*;
import com.firemonitoring.api.dto.*;
import com.firemonitoring.api.repository.CameraRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URI;
import java.time.Instant;
import java.util.List;

@Service
public class CameraService {
    private final CameraRepository cameras;
    private final String whepBaseUrl;
    private final String hlsBaseUrl;
    private final long ticketTtlSeconds;

    public CameraService(CameraRepository cameras,
                         @Value("${app.media.whep-base-url}") String whepBaseUrl,
                         @Value("${app.media.hls-base-url}") String hlsBaseUrl,
                         @Value("${app.media.ticket-ttl-seconds}") long ticketTtlSeconds) {
        this.cameras = cameras;
        this.whepBaseUrl = stripSlash(whepBaseUrl);
        this.hlsBaseUrl = stripSlash(hlsBaseUrl);
        this.ticketTtlSeconds = ticketTtlSeconds;
    }

    @Transactional(readOnly = true)
    public List<CameraResponse> list() { return cameras.findAll().stream().map(CameraService::map).toList(); }

    @Transactional
    public CameraResponse create(CameraUpsert request) {
        String sourceUri = blankToNull(request.sourceUri());
        if ((request.sourceType() == SourceType.NETWORK_RTSP || request.sourceType() == SourceType.DEMO_FILE)
                && sourceUri == null) {
            throw new BadRequestException("sourceUri is required for network and demo-file cameras");
        }
        if (request.sourceType() == SourceType.NETWORK_RTSP && !sourceUri.toLowerCase().startsWith("rtsp://")) {
            throw new BadRequestException("Network camera sourceUri must use rtsp://");
        }
        return map(cameras.save(new CameraEntity(request.name().trim(), request.sourceType(), sourceUri, request.targetFps())));
    }

    @Transactional
    public CameraProbeResult probe(Long id) {
        CameraEntity camera = get(id);
        Instant checkedAt = Instant.now();
        boolean reachable = switch (camera.getSourceType()) {
            case INTEGRATED, USB -> true;
            case DEMO_FILE -> camera.getSourceUri() != null;
            case NETWORK_RTSP -> camera.getSourceUri() != null && camera.getSourceUri().startsWith("rtsp://");
        };
        camera.recordProbe(reachable, checkedAt);
        cameras.save(camera);
        String message = reachable
                ? "Configuration accepted (MVP probe stub; media-plane verification is pending)"
                : "Camera source is not configured";
        return new CameraProbeResult(reachable, checkedAt, null, null,
                reachable ? camera.getTargetFps() : null, message);
    }

    @Transactional(readOnly = true)
    public StreamTicket createStreamTicket(Long id) {
        CameraEntity camera = get(id);
        Instant expiresAt = Instant.now().plusSeconds(ticketTtlSeconds);
        return new StreamTicket(expiresAt,
                URI.create(whepBaseUrl + "/" + camera.getStreamKey() + "/whep"),
                URI.create(hlsBaseUrl + "/" + camera.getStreamKey() + "/index.m3u8"));
    }

    private CameraEntity get(Long id) {
        return cameras.findById(id).orElseThrow(() -> new ResourceNotFoundException("Camera not found: " + id));
    }

    private static CameraResponse map(CameraEntity camera) {
        return new CameraResponse(camera.getId(), camera.getName(), camera.getSourceType(), camera.getStreamKey(),
                mask(camera.getSourceUri()), camera.getStatus(), camera.getLastSeenAt());
    }

    private static String mask(String source) {
        if (source == null || source.isBlank()) return null;
        try {
            URI uri = URI.create(source);
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
