package com.firemonitoring.api.dto;

import java.util.List;

public record UserResponse(Long id, String username, String displayName, List<String> roles) {}
