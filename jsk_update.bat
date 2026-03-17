powershell -Command "Expand-Archive -Path 'C:\Users\Tsalyer\Downloads\road-tablet-updates.zip' -DestinationPath 'C:\Users\Tsalyer\Downloads' -Force"

powershell -Command "Expand-Archive -Path 'C:\Users\Tsalyer\Downloads\road-tablet-updates\zulu25-0-1.zip' -DestinationPath 'C:\Users\Tsalyer\Downloads\road-tablet-updates' -Force"

Copy-Item "C:\Users\Tsalyer\Downloads\road-tablet-updates\dld-road-tablet.jar" "C:\road-tablet\"

Copy-Item "C:\Users\Tsalyer\Downloads\road-tablet-updates\launch.bat" "C:\road-tablet\"

Remove-Item "C:\road-tablet\libs\javafx-base-11.0.2.jar"
Remove-Item "C:\road-tablet\libs\javafx-base-11.0.2-win.jar"
Remove-Item "C:\road-tablet\libs\javafx-controls-11.0.2.jar"
Remove-Item "C:\road-tablet\libs\javafx-controls-11.0.2-win.jar"
Remove-Item "C:\road-tablet\libs\javafx-fxml-11.0.2.jar"
Remove-Item "C:\road-tablet\libs\javafx-fxml-11.0.2-win.jar"
Remove-Item "C:\road-tablet\libs\javafx-graphics-11.0.2.jar"
Remove-Item "C:\road-tablet\libs\javafx-graphics-11.0.2-win.jar"
Remove-Item "C:\road-tablet\libs\javafx-media-11.0.2.jar"
Remove-Item "C:\road-tablet\libs\javafx-media-11.0.2-win.jar"
Remove-Item "C:\road-tablet\libs\javafx-swing-11.0.2.jar"
Remove-Item "C:\road-tablet\libs\javafx-swing-11.0.2-win.jar"
Remove-Item "C:\road-tablet\libs\javafx-web-11.0.2.jar"
Remove-Item "C:\road-tablet\libs\javafx-web-11.0.2-win.jar"
Remove-Item "C:\road-tablet\libs\log4j-api-2.24.3.jar"
Remove-Item "C:\road-tablet\libs\log4j-core-2.24.3.jar"

Copy-Item "C:\Users\Tsalyer\Downloads\road-tablet-updates\libs\log4j-core-2.25.2.jar" "C:\road-tablet\libs\"
Copy-Item "C:\Users\Tsalyer\Downloads\road-tablet-updates\libs\log4j-api-2.25.2.jar" "C:\road-tablet\libs\"

Copy-Item "C:\Users\Tsalyer\Downloads\road-tablet-updates\zulu25-0-1" "C:\road-tablet\zulu25-0-1\" -Recurse
