package com.firemonitoring.api.events;

public class EventParseException extends RuntimeException {
    public EventParseException(String message) { super(message); }
    public EventParseException(String message, Throwable cause) { super(message, cause); }
}
