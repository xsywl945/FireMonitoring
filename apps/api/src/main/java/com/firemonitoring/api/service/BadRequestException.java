package com.firemonitoring.api.service;

public class BadRequestException extends RuntimeException {
    public BadRequestException(String message) { super(message); }
}
