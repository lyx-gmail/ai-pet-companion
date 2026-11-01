"""Keep installed assets and vendor download metadata intact on pet boot."""


def apply(source,replace):
    path = source/'main/application.cc'
    text = path.read_text(encoding='utf-8')
    marker = 'Pet firmware: preserving installed assets and pending vendor download metadata'
    if marker in text:
        return
    method = text.index('void Application::CheckAssetsVersion() {')
    start = text.index('    Settings settings("assets", true);',method)
    end = text.index('    // Apply assets',start)
    original = text[start:end]
    if 'assets.Download(' not in original or 'settings.EraseKey("download_url")' not in original:
        raise RuntimeError('Asset update overlay context changed')
    replace(path,original,'    ESP_LOGI(TAG, "'+marker+'");\n\n')
