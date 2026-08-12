package com.firemonitoring.api.events;

import java.util.List;

public record EvidenceDetection(String className, Double confidence, List<Double> bboxXyxy) {}
