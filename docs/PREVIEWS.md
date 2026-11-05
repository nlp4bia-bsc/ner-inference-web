# Phase 2 visual checks

Captured by Chromium against the actual local application and prefixed document
APIs. These screenshots use a synthetic fixture with seven explicitly controlled
annotations, including nested, equal-boundary and crossing spans; they are not
clinical predictions. The form's catalog uses a test-only HTTP fixture. No such
model/catalog override is exposed in production.

## Home · 1440px

![Desktop request form](previews/home-desktop.png)

## Explorer · 1440px

![Desktop explorer with overlapping spans and individual mention details](previews/viewer-desktop.png)

## Explorer · 390px

![Mobile explorer with document controls, original text and annotation details](previews/viewer-mobile.png)

Functional responsive tests additionally ran at 320, 375, 768, 1024, 1920 and
2560px. Every overlap was selected in both the document/list representations;
keyboard region selection exposed all four annotations in the densest region.

# V3 additions

The following controlled synthetic captures include the input tabs, persistent
collapsible progress, server-clock countdown, document tree, individual downloads
and synchronized annotation-table controls. They are test fixtures, not clinical
model results or a BSC production deployment.

![V3 request form](previews/v3-home-desktop.png)

![V3 desktop workspace](previews/v3-viewer-desktop.png)

![V3 mobile workspace](previews/v3-viewer-mobile.png)
