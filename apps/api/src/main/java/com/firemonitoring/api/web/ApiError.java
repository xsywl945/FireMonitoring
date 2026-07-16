package com.firemonitoring.api.web;

import java.time.Instant;
import java.util.Map;

public record ApiError(Instant timestamp, int status, String code, String message,
                       String path, String traceId, Map<String, String> fieldErrors) {
    public static ApiError of(int status, String code, String message, HttpServletRequestView request) {
        return new ApiError(Instant.now(), status, code, message, request.path(), request.traceId(), null);
    }

    public record HttpServletRequestView(String path, String traceId) {}
}
