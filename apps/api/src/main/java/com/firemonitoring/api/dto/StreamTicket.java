package com.firemonitoring.api.dto;

import java.net.URI;
import java.time.Instant;

public record StreamTicket(Instant expiresAt, URI whepUrl, URI hlsUrl) {}
