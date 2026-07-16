package com.firemonitoring.api.dto;

public record AuthResponse(String accessToken, long expiresInSeconds, UserResponse user) {}
